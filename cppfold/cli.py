import sys
import os
import subprocess
from .parser import CppErrorParser

def main():
    args = sys.argv[1:]
    parser = CppErrorParser()

    if not args:
        # 模式1：管道模式 (e.g., catkin_make 2>&1 | cppfold)
        # 如果没有跟任何参数，就从标准输入读取
        if sys.stdin.isatty():
            print("Usage: cppfold <build_command> OR <build_command> 2>&1 | cppfold")
            sys.exit(1)
        
        try:
            parser.process_stream(sys.stdin)
        except KeyboardInterrupt:
            pass
        finally:
            parser.print_dictionary()
            sys.exit(0)

    else:
        # 模式2：包装器模式 (e.g., cppfold catkin_make -j4)
        # 强制编译器输出颜色 (非常重要)
        env = os.environ.copy()
        env['FORCE_COLOR'] = '1'
        env['GCC_COLORS'] = 'error=01;31:warning=01;35:note=01;36:caret=01;32:locus=01:quote=01'
        env['CLANG_FORCE_COLOR_DIAGNOSTICS'] = '1'

        try:
            # 启动子进程，将 stderr 合并到 stdout 一起实时读取
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # 把报错和正常输出合并
                text=True,                # 以字符串模式读取
                env=env,
                bufsize=1
            )

            # 实时读取并处理
            parser.process_stream(process.stdout)
            
            # 等待子进程结束并获取状态码
            process.wait()
            
            # 打印字典
            parser.print_dictionary()
            
            # 完美转发原始命令的状态码
            sys.exit(process.returncode)

        except FileNotFoundError:
            print(f"\033[91mError: Command '{args[0]}' not found.\033[0m")
            sys.exit(1)
        except KeyboardInterrupt:
            # 允许用户按 Ctrl+C 中断编译
            sys.exit(130)

if __name__ == "__main__":
    main()