@echo off
rem HooH launcher -- thin forwarder to ace.cmd.
rem
rem Why this file exists at all: the product was renamed HooH, but `ace.cmd` is the
rem name every existing shortcut, scheduled task and muscle-memory typing still uses.
rem Renaming it would break those for no benefit, so BOTH names ship:
rem
rem     hooh    <- new, canonical
rem     ace     <- kept forever as an alias (forwards to the same entry point)
rem
rem `ace.cmd` stays the ONLY place that resolves an interpreter and picks the
rem frontend. This file must never grow a second copy of that logic -- one
rem launcher, one dispatcher, two names.
rem
rem Why `cmd /c` and NOT `call`:
rem     call "%~dp0ace.cmd" %*      -> exit -1073740791 (0xC0000409, stack buffer
rem                                    overrun) as soon as the Ink frontend runs.
rem     cmd /c "%~dp0ace.cmd" %*     -> exit 0, works.
rem A batch `call` keeps the child INSIDE this cmd.exe process, and ace.cmd's
rem pushd/node/popd sequence then dies on the way out. Running ace.cmd as a real
rem child process avoids the nested-batch path entirely. Do not "simplify" this
rem back to `call` -- it looks tidier and crashes.
rem ASCII-ONLY ON PURPOSE. Do not add non-ASCII text (Chinese, emoji, smart
rem quotes) to this file, not even inside rem comments or echo strings. cmd.exe
rem tracks its position in a batch file by byte offset, and multi-byte characters
rem break that bookkeeping when the console code page changes. See ace.cmd's own
rem header for the full explanation.
rem
rem Usage: hooh [args]    e.g.  hooh --mock  |  hooh --install-ui  |  hooh --setup

cmd /c ""%~dp0ace.cmd" %*"
exit /b %ERRORLEVEL%
