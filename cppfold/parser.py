import re
import sys

class CppErrorParser:
    def __init__(self):
        self.type_map = {}
        self.counter = 1
        # 默认丢弃这些无意义且极长的类型
        self.ignore_patterns = ["allocator<", "char_traits<"]

    def fold_line(self, line):
        result = []
        i = 0
        length = len(line)
        
        while i < length:
            match = re.match(r'([a-zA-Z0-9_:]+)<', line[i:])
            if match:
                base_name = match.group(1)
                if base_name.endswith("operator") or "operator<" in base_name:
                    result.append(line[i])
                    i += 1
                    continue
                
                start_idx = i + len(base_name)
                bracket_count = 1
                j = start_idx + 1
                
                while j < length and bracket_count > 0:
                    if line[j] == '<': bracket_count += 1
                    elif line[j] == '>': bracket_count -= 1
                    j += 1
                
                if bracket_count == 0:
                    inner_content = line[start_idx+1 : j-1]
                    
                    # 规则1：如果内部很短，不折叠
                    if len(inner_content) < 15:
                        result.append(f"{base_name}<{inner_content}>")
                        i = j
                        continue

                    # 规则2：直接吃掉 allocator
                    if any(p in base_name for p in self.ignore_patterns):
                        return "" # 返回空表示这个部分被忽略

                    folded_inner = self.fold_line(inner_content)
                    
                    type_id = f"T{self.counter}"
                    self.counter += 1
                    self.type_map[type_id] = folded_inner
                    
                    # 给代号上高亮青蓝色
                    color_id = f"\033[96m[{type_id}]\033[0m"
                    result.append(f"{base_name}<{color_id}>")
                    i = j
                else:
                    result.append(line[i])
                    i += 1
            else:
                result.append(line[i])
                i += 1
                
        return "".join(result)

    def process_stream(self, stream):
        """实时处理输入流，避免等待编译结束"""
        for line in stream:
            folded_line = self.fold_line(line)
            sys.stdout.write(folded_line)
            sys.stdout.flush()

    def print_dictionary(self):
        if not self.type_map:
            return
        print("\n\033[93m" + "="*50 + "\033[0m")
        print("\033[1;96m[ cppfold: Template Dictionary ]\033[0m")
        for tid, content in self.type_map.items():
            print(f"\033[96m[{tid}]\033[0m = {content}")
        print("\033[93m" + "="*50 + "\033[0m\n")