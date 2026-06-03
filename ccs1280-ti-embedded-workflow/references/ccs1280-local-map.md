# C:\ti\ccs1280 Local Map

Use this reference only when a task needs concrete local paths or component facts.

## Base Inventory

- Base path: `C:\ti\ccs1280`
- Top-level items: `ccs`, `xdctools_3_62_01_16_core`, `Code Composer Studio 12.8.0.lnk`
- Approximate inventory from 2026-06-03: 72,064 files, 5.96 GB
- Largest CCS subtrees:
  - `ccs\tools`: compilers, Node, SysConfig, tiobj2bin
  - `ccs\ccs_base`: DebugServer, emulation, targetdb, device support, scripting
  - `ccs\eclipse`: CCS/Eclipse IDE and plugins
  - `ccs\F28335_PID`: user workspace/projects

## Confirmed Tool Versions

- CCS IDE: 12.8.0
- DebugServer/DS: 12.8.0.3471
- TI Emulator support: 12.8.0.00189
- C2000 compiler: `ti-cgt-c2000_22.6.1.LTS`, `cl2000.exe --compiler_revision` -> `22.6.1`
- TI Arm Clang: `ti-cgt-armllvm_3.2.2.LTS`, `tiarmclang.exe --version` -> `TI Arm Clang Compiler 3.2.2.LTS`
- MSP430 compiler: `ti-cgt-msp430_21.6.1.LTS`, `cl430.exe --compiler_revision` -> `21.6.1`
- C6000 compiler: `ti-cgt-c6000_8.3.12`, `cl6x.exe --compiler_revision` -> `8.3.12`
- SysConfig CLI: `ccs\utils\sysconfig_1.21.0\sysconfig_cli.bat --version` -> `1.21.0+3721`
- XDCtools: `xdctools_3_62_01_16_core`
- Node.js component: 18.16.0
- SEGGER J-Link component: 7.96.0

## Product Families

Installed families include MSP430, MSP432, MSPM0, wireless connectivity, C28/C2000, TM4C, Hercules, Sitara, Sitara MCU, OMAP/Davinci, C55, C6000, Keystone, mmWave, Digital Power, and PGA.

## Debug and Flash

- DebugServer bin: `C:\ti\ccs1280\ccs\ccs_base\DebugServer\bin`
- Notable files: `DSLite.exe`, `DebugServer.dll`, `Flash28xx.dll`, `FlashC2000F021.dll`, `FlashMSP430.dll`, `FlashMSPM0.dll`, `FlashPythonSubprocess.exe`, `GTIRemoteProxyServer.exe`
- Scripting roots:
  - `C:\ti\ccs1280\ccs\ccs_base\scripting`
  - `C:\ti\ccs1280\ccs\scripting`
- Useful examples observed: `DebugServerExamples\f28335_flash.js`, `loadti`, `uniflash`, MSP430 memory/breakpoint/load examples, Node debugger examples.

## Target Database

- Root: `C:\ti\ccs1280\ccs\ccs_base\common\targetdb`
- Subfolders: `devices`, `connections`, `boards`, `drivers`, `cpus`, `routers`, `Modules`, `options`
- Observed connection files include XDS100, XDS110, XDS2xx, XDS560, Blackhawk, SEGGER J-Link, MSP430 USB/FET, Stellaris ICDI, and UART.

## Known User Workspace

Workspace path: `C:\ti\ccs1280\ccs\F28335_PID`

Projects:

- `8065_d9_board_test_ccs`
  - Key files: `common\d9_board_test.c`, `common\protocol_8065.c`, `platform_f28034.c`, `main_f28034.c`, `F28034.cmd`, `f28034_ram_lnk.cmd`, `targetConfigs\TMS320F28034.ccxml`
  - Meaning: F28034-based 8065/D9 board test project.
- `F28335_PID`
  - Key files: `src\PID_DEMO.c`, `cmd\28335_RAM_lnk.cmd`, `targetConfigs\TMS320F28335.ccxml`, DSP2833x headers/sources.
  - Meaning: F28335 PID/ADC/ePWM example project.
- `28034test`
  - Key files: DSP2803x common/source/header files, F28034/F28035 linker scripts, `main.c`.
  - Meaning: F28034/F28035 support/template project.
- `TMS320F28034_Project`
  - Key files: `.ccsproject`, `.cproject`, `28034_RAM_lnk.cmd`, `main.c`.
  - Meaning: minimal F28034 skeleton; `main.c` currently returns 0.

## Report Artifact

A Chinese analysis report was generated at:

`C:\Users\hjs\Desktop\CCS1280_能力分析报告.md`
