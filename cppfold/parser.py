import re
import sys

class CppErrorParser:
    def __init__(self):
        self.type_map = {}
        self.counter = 1
        # 常见无用且极长的 STL 类型，直接丢弃
        self.ignore_patterns = ["allocator<", "char_traits<", "default_delete<"]
        
        # 匹配 GCC/Clang 报错起始行的正则表达式 (例如: /path/main.cpp:10:5: error: ...)
        self.error_start_pattern = re.compile(r'(.*?:\d+:\d+: (?:error|warning):|CMake Error)')

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
                    
                    if len(inner_content) < 15:
                        result.append(f"{base_name}<{inner_content}>")
                        i = j
                        continue

                    if any(p in base_name for p in self.ignore_patterns):
                        return ""

                    folded_inner = self.fold_line(inner_content)
                    
                    type_id = f"T{self.counter}"
                    self.counter += 1
                    # 避免完全相同的类型重复生成 T1, T2
                    # 这里可以做一个小优化：如果 folded_inner 已经存在，复用旧的 ID
                    existing_id = next((k for k, v in self.type_map.items() if v == folded_inner), None)
                    if existing_id:
                        type_id = existing_id
                        self.counter -= 1
                    else:
                        self.type_map[type_id] = folded_inner
                    
                    # 颜色：青色高亮代号
                    color_id = f"\033[1;36m[{type_id}]\033[0m"
                    result.append(f"{base_name}<{color_id}>")
                    i = j
                else:
                    result.append(line[i])
                    i += 1
            else:
                result.append(line[i])
                i += 1
                
        return "".join(result)

    def print_dictionary_and_reset(self):
        """打印当前收集到的局部字典，并重置计数器"""
        output = ""
        if self.type_map:
            output += "\n\033[93m" + "-"*60 + "\033[0m\n"
            output += "\033[1;96m[ Template Dictionary (Local) ]\033[0m\n"
            for tid, content in self.type_map.items():
                output += f"  \033[1;36m[{tid}]\033[0m = {content}\n"
            output += "\033[93m" + "-"*60 + "\033[0m\n\n"
            
        # 核心：重置字典！
        self.type_map.clear()
        self.counter = 1
        return output

    def process_stream(self, stream, output_list=None):
        """
        stream: 输入的可迭代对象(行)
        output_list: 如果传入列表，则将结果存入列表（用于分页），否则直接打印
        """
        for line in stream:
            # 如果检测到新的错误块，先把上一个报错的字典打印出来
            # 清除 ANSI 颜色代码以便正则匹配
            clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line)
            
            if self.error_start_pattern.search(clean_line):
                dict_str = self.print_dictionary_and_reset()
                if dict_str:
                    if output_list is not None:
                        output_list.append(dict_str)
                    else:
                        sys.stdout.write(dict_str)

            folded_line = self.fold_line(line)
            
            if output_list is not None:
                output_list.append(folded_line)
            else:
                sys.stdout.write(folded_line)
                sys.stdout.flush()
                
        # 处理结束后，确保最后一块字典也被打印
        dict_str = self.print_dictionary_and_reset()
        if dict_str:
            if output_list is not None:
                output_list.append(dict_str)
            else:
                sys.stdout.write(dict_str)