-- Запускающая часть пакета .app.
--
-- Исполняемым файлом пакета обязан быть настоящий Mach-O: с macOS 15
-- LaunchServices отказывается открывать приложение, у которого на этом
-- месте лежит скрипт, — сначала предлагает поставить Rosetta, а затем
-- возвращает -10669. Компилировать что-то своё для этого не нужно:
-- osacompile делает пакет вокруг стандартного applet'а, а тот входит
-- в macOS и собран сразу под обе архитектуры.
--
-- Вся работа по-прежнему в Contents/Resources/launcher; здесь только
-- запуск. Процесс отвязывается и продолжает жить сам: applet после
-- этого завершается, а значок в строке меню поднимает уже python.

on run
	set here to POSIX path of (path to me)
	set launcher to quoted form of (here & "Contents/Resources/launcher")
	do shell script "/usr/bin/nohup " & launcher & " > /dev/null 2>&1 &"
end run
