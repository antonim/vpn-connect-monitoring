"""Минимальный мост к Objective-C через ctypes.

Значку в строке меню нужен AppKit, а привязок к нему в стандартной
поставке Python нет. Обычный ответ на это — PyObjC, но ставить его
некуда: Apple убрала PyObjC вместе с системным Python 2.7 в macOS 12.3,
в Command Line Tools его нет, а Homebrew-питон помечен externally-managed
и pip в него не пускает. Виртуальное окружение ради одного значка тянет
за собой сеть при установке и ломается при обновлении интерпретатора.

Поэтому обращаемся к среде выполнения Objective-C напрямую: libobjc
и фреймворки — это обычные динамические библиотеки, а ctypes входит
в стандартную библиотеку. Нужного здесь — вызов метода, создание строки
и объявление класса с обработчиками — хватает на полторы сотни строк.

Тонкости, из-за которых код выглядит именно так:

* objc_msgSend объявлена вариадической, и вызывать её без точного
  описания типов нельзя: на arm64 переменные аргументы передаются иначе,
  чем именованные, и вызов молча испортит стек. Поэтому под каждую
  подпись создаётся отдельный прототип CFUNCTYPE.
* Ни один вызываемый здесь метод не возвращает структуру, поэтому
  objc_msgSend_stret не нужна — иначе пришлось бы разделять пути для
  Intel и Apple silicon.
* Объекты, полученные не через alloc, автоосвобождаются. Всё, что должно
  пережить текущий проход цикла событий, удерживаем явным retain:
  забытый retain на NSStatusItem — классическая причина значка,
  который исчезает через секунду после появления.
* Питоновские объекты-обработчики нужно удерживать от сборки мусора
  на стороне Python: среда выполнения Objective-C держит на них только
  сырой указатель и о сборщике ничего не знает.
"""

import ctypes

try:
    _objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.dylib")
    ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
    ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AppKit.framework/AppKit")
except OSError as exc:
    # cli.py ловит ImportError и предлагает режим без графики.
    raise ImportError("не удалось загрузить AppKit: %s" % exc)

ID = ctypes.c_void_p
SEL = ctypes.c_void_p
CLASS = ctypes.c_void_p
BOOL = ctypes.c_bool
NSInteger = ctypes.c_long
NSUInteger = ctypes.c_ulong
CGFloat = ctypes.c_double

_objc.objc_getClass.restype = CLASS
_objc.objc_getClass.argtypes = [ctypes.c_char_p]
_objc.sel_registerName.restype = SEL
_objc.sel_registerName.argtypes = [ctypes.c_char_p]
_objc.objc_allocateClassPair.restype = CLASS
_objc.objc_allocateClassPair.argtypes = [CLASS, ctypes.c_char_p, ctypes.c_size_t]
_objc.objc_registerClassPair.restype = None
_objc.objc_registerClassPair.argtypes = [CLASS]
_objc.class_addMethod.restype = BOOL
_objc.class_addMethod.argtypes = [CLASS, SEL, ctypes.c_void_p, ctypes.c_char_p]
_objc.class_getInstanceMethod.restype = ctypes.c_void_p
_objc.class_getInstanceMethod.argtypes = [CLASS, SEL]
_objc.method_setImplementation.restype = ctypes.c_void_p
_objc.method_setImplementation.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

_classes = {}
_selectors = {}
_prototypes = {}

# Сюда складываем всё, что должно жить, пока жив процесс: обработчики
# и созданные классы. Без этого Python соберёт объект, на который
# Objective-C держит указатель, и следующий клик уронит программу.
_keepalive = []


def cls(name):
    """Класс по имени. Возвращает None, если такого класса нет."""
    if name not in _classes:
        _classes[name] = _objc.objc_getClass(name.encode("ascii"))
    return _classes[name]


def sel(name):
    """Селектор по имени, например "setTitle:"."""
    if name not in _selectors:
        _selectors[name] = _objc.sel_registerName(name.encode("ascii"))
    return _selectors[name]


def msg(receiver, selector, *args, **kwargs):
    """Вызов метода Objective-C.

    restype и argtypes описывают подпись; по умолчанию метод без
    аргументов, возвращающий объект.
    """
    restype = kwargs.pop("restype", ID)
    argtypes = tuple(kwargs.pop("argtypes", ()))
    if kwargs:
        raise TypeError("неизвестный параметр: %s" % ", ".join(kwargs))
    if len(argtypes) != len(args):
        raise TypeError("описано %d аргументов, передано %d" % (len(argtypes), len(args)))

    key = (restype, argtypes)
    if key not in _prototypes:
        _prototypes[key] = ctypes.CFUNCTYPE(restype, ID, SEL, *argtypes)
    fn = ctypes.cast(_objc.objc_msgSend, _prototypes[key])
    return fn(receiver, sel(selector) if isinstance(selector, str) else selector, *args)


def nsstring(text):
    """NSString из питоновской строки."""
    return msg(cls("NSString"), "stringWithUTF8String:",
               text.encode("utf-8"), argtypes=[ctypes.c_char_p])


def pystring(nsstr):
    """Питоновская строка из NSString."""
    if not nsstr:
        return ""
    raw = msg(nsstr, "UTF8String", restype=ctypes.c_char_p)
    return raw.decode("utf-8") if raw else ""


def new(class_name, *args, **kwargs):
    """alloc + init… с указанным инициализатором (по умолчанию init)."""
    initializer = kwargs.pop("initializer", "init")
    obj = msg(cls(class_name), "alloc")
    return msg(obj, initializer, *args, **kwargs)


def retain(obj):
    """Удержать объект на всё время работы программы."""
    return msg(obj, "retain")


def define_class(name, methods):
    """Объявить класс — наследник NSObject с питоновскими обработчиками.

    methods: {"селектор:": (функция, "подпись")}. Функция получает
    (self, _cmd, аргументы…) — так устроен вызов метода в Objective-C.
    Подпись — строка кодировки типов: "v@:@" значит «ничего не
    возвращает, принимает объект».
    """
    handle = _objc.objc_allocateClassPair(cls("NSObject"), name.encode("ascii"), 0)
    if not handle:
        raise RuntimeError("класс %s уже объявлен" % name)

    for selector, (func, signature) in methods.items():
        # По числу двоеточий в селекторе восстанавливаем число аргументов:
        # у метода их всегда на два больше — self и _cmd.
        arg_count = selector.count(":")
        prototype = ctypes.CFUNCTYPE(*([None, ID, SEL] + [ID] * arg_count))
        imp = prototype(func)
        _keepalive.append(imp)
        if not _objc.class_addMethod(handle, sel(selector),
                                     ctypes.cast(imp, ctypes.c_void_p),
                                     signature.encode("ascii")):
            raise RuntimeError("не удалось добавить метод %s" % selector)

    _objc.objc_registerClassPair(handle)
    _keepalive.append(handle)
    return handle


def set_bundle_identifier(identifier):
    """Выдать процесс за приложение с указанным идентификатором.

    Нужно уведомлениям. Центр уведомлений берёт имя и значок отправителя
    у главного бандла процесса, а он у нас чужой: Python во фреймворковой
    сборке всегда объявляет главным свой Python.app, и это не обходится
    ни расположением файлов внутри пакета, ни символическими ссылками,
    ни копией бинарника — проверено, все три дают org.python.python.
    Без подмены уведомления приходят от «Python» с его ракетой.

    Подменяется реализация -[NSBundle bundleIdentifier] внутри своего
    процесса; на другие программы это не влияет. Идентификатор должен
    принадлежать зарегистрированному в системе приложению, иначе центр
    уведомлений отбрасывает сообщение молча.

    Возвращает False, если подменить не удалось.
    """
    global _bundle_identifier_imp

    method = _objc.class_getInstanceMethod(cls("NSBundle"), sel("bundleIdentifier"))
    if not method:
        return False

    prototype = ctypes.CFUNCTYPE(ID, ID, SEL)
    # Замыкание держим и в глобальной переменной, и в _keepalive:
    # Objective-C хранит только сырой указатель и о сборщике мусора
    # не знает, а собранная функция уронила бы процесс при вызове.
    _bundle_identifier_imp = prototype(lambda _self, _cmd: nsstring(identifier))
    _keepalive.append(_bundle_identifier_imp)

    _objc.method_setImplementation(
        method, ctypes.cast(_bundle_identifier_imp, ctypes.c_void_p)
    )
    return pystring(msg(msg(cls("NSBundle"), "mainBundle"), "bundleIdentifier")) == identifier


_bundle_identifier_imp = None
