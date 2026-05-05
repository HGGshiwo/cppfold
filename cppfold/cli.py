import sys
import os
import pty
import subprocess
import select
from .parser import CppErrorParser

def page_output(text_lines):
    """调用系统的 less 命令实现分页显示"""
    text = "".join(text_lines)
    try:
        # -R 允许显示 ANSI 颜色, -F 如果一页能装下则直接退出, -X 不清屏
        process = subprocess.Popen(['less', '-R', '-F', '-X'], stdin=subprocess.PIPE, text=True)
        process.communicate(text)
    except FileNotFoundError:
        # 如果没有 less 命令，退化为直接打印
        sys.stdout.write(text)

def main():
    # 简单的参数解析：如果有 --page，则开启分页模式
    args = sys.argv[1:]
    use_pager = False
    if '--page' in args:
        use_pager = True
        args.remove('--page')

    if not args:
        print("Usage: cppfold [--page] <build_command>")
        sys.exit(1)

    parser = CppErrorParser()
    buffered_output = [] if use_pager else None

    # 使用 pty (伪终端) 启动子进程，这是保留编译器颜色的终极杀器
    master_fd, slave_fd = pty.openpty()

    try:
        process = subprocess.Popen(
            args,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True
        )
    except FileNotFoundError:
        print(f"\033[91mError: Command '{args[0]}' not found.\033[0m")
        sys.exit(1)

    os.close(slave_fd) # 父进程不需要 slave

    try:
        # 非阻塞读取 PTY 输出
        while True:
            r, _, _ = select.select([master_fd], [], [], 0.1)
            if master_fd in r:
                try:
                    data = os.read(master_fd, 4096)
                    if not data:
                        break
                    
                    # 将 byte 转换为 text，按行分割但保留换行符
                    text = data.decode('utf-8', errors='replace')
                    lines = [line + '\n' for line in text.split('\n')]
                    # 如果末尾刚好是 \n，split 会多出一个空字符串
                    if lines[-1] == '\n':
                        lines.pop()

                    # 逐行处理
                    parser.process_stream(lines, output_list=buffered_output)

                except OSError:
                    # PTY 在子进程结束时通常会抛出 OSError
                    break
            
            # 检查子进程是否结束
            if process.poll() is not None:
                # 确保读取完最后的数据
                try:
                    data = os.read(master_fd, 4096)
                    if data:
                        text = data.decode('utf-8', errors='replace')
                        lines = [line + '\n' for line in text.split('\n')]
                        if lines[-1] == '\n': lines.pop()
                        parser.process_stream(lines, output_list=buffered_output)
                except OSError:
                    pass
                break

    except KeyboardInterrupt:
        pass
    finally:
        os.close(master_fd)
        
        # 如果还在字典里残留了最后的错误，刷出来
        dict_str = parser.print_dictionary_and_reset()
        if dict_str:
            if buffered_output is not None:
                buffered_output.append(dict_str)
            else:
                sys.stdout.write(dict_str)

        # 核心：如果是 --page 模式，在此刻统一调用 less 显示
        if use_pager and buffered_output:
            page_output(buffered_output)

    sys.exit(process.returncode)

if __name__ == "__main__":
    main()