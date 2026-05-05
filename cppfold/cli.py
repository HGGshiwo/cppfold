import sys
import os
import pty
import subprocess
import select
from .parser import GccSemanticParser

def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: cppfold <build_command>")
        sys.exit(1)

    parser = GccSemanticParser()
    has_error = False
    
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

    os.close(slave_fd)

    try:
        while True:
            r, _, _ = select.select([master_fd], [], [], 0.1)
            if master_fd in r:
                try:
                    data = os.read(master_fd, 4096)
                    if not data: break
                    text = data.decode('utf-8', errors='replace')
                    lines = [line + '\n' for line in text.split('\n')]
                    if lines[-1] == '\n': lines.pop()

                    for line in lines:
                        # 检查是否出现 error:，一旦出现，激活报错状态
                        if "error:" in line:
                            has_error = True
                        
                        if has_error:
                            # 错误状态下：不再打印任何东西到屏幕，全部喂给语义引擎去分析
                            parser.process_line(line)
                        else:
                            # 正常状态下：原样打印编译进度，不做任何干预
                            sys.stdout.write(line)
                            sys.stdout.flush()

                except OSError:
                    break
            
            if process.poll() is not None:
                try:
                    data = os.read(master_fd, 4096)
                    if data:
                        text = data.decode('utf-8', errors='replace')
                        lines = [line + '\n' for line in text.split('\n')]
                        if lines[-1] == '\n': lines.pop()
                        for line in lines:
                            if "error:" in line: has_error = True
                            if has_error: parser.process_line(line)
                            else: sys.stdout.write(line)
                except OSError:
                    pass
                break

    except KeyboardInterrupt:
        pass
    finally:
        os.close(master_fd)
        
        # === 核心：如果捕获到了错误，渲染人话报告并用 less 打开 ===
        if has_error:
            report_text = parser.generate_human_report()
            if report_text.strip():
                try:
                    # 调用系统的 pager
                    less_proc = subprocess.Popen(['less', '-R', '-F', '-X'], stdin=subprocess.PIPE, text=True)
                    less_proc.communicate(report_text)
                except FileNotFoundError:
                    sys.stdout.write(report_text)

    sys.exit(process.returncode)

if __name__ == "__main__":
    main()