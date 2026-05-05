import re
import sys

class GccSemanticParser:
    def __init__(self):
        self.type_map = {}
        self.counter = 1
        self.ignore_patterns = ["allocator<", "char_traits<", "default_delete<"]
        
        # 缓存当前正在收集的错误块
        self.current_block = {
            "main_error": None,
            "notes": [],
            "stack_trace": [],
            "raw_lines": [] # 如果解析失败，保留原始折叠输出
        }
        self.all_blocks = []

    def _fold_type(self, type_str):
        """核心递归折叠算法，处理 < > 和 [with ]"""
        result = []
        i = 0
        length = len(type_str)
        
        while i < length:
            # 处理 [with ...]
            if type_str[i:].startswith('[with '):
                start_idx = i
                bracket_count = 1
                j = start_idx + 6
                while j < length and bracket_count > 0:
                    if type_str[j] == '[': bracket_count += 1
                    elif type_str[j] == ']': bracket_count -= 1
                    j += 1
                if bracket_count == 0:
                    inner_content = type_str[start_idx+6 : j-1]
                    folded_inner = self._fold_type(inner_content)
                    
                    tid = f"T{self.counter}"
                    self.counter += 1
                    existing = next((k for k,v in self.type_map.items() if v == folded_inner), None)
                    if existing:
                        tid = existing
                        self.counter -= 1
                    else:
                        self.type_map[tid] = folded_inner
                    
                    result.append(f"[with \033[1;36m[{tid}]\033[0m]")
                    i = j
                    continue

            # 处理 < >
            match = re.match(r'([a-zA-Z0-9_:]+)<', type_str[i:])
            if match:
                base = match.group(1)
                if base.endswith("operator") or "operator<" in base:
                    result.append(type_str[i])
                    i += 1
                    continue
                start_idx = i + len(base)
                bracket_count = 1
                j = start_idx + 1
                while j < length and bracket_count > 0:
                    if type_str[j] == '<': bracket_count += 1
                    elif type_str[j] == '>': bracket_count -= 1
                    j += 1
                if bracket_count == 0:
                    inner_content = type_str[start_idx+1 : j-1]
                    if len(inner_content) < 15:
                        result.append(f"{base}<{inner_content}>")
                        i = j
                        continue
                    if any(p in base for p in self.ignore_patterns):
                        return ""
                        
                    folded_inner = self._fold_type(inner_content)
                    tid = f"T{self.counter}"
                    self.counter += 1
                    existing = next((k for k,v in self.type_map.items() if v == folded_inner), None)
                    if existing:
                        tid = existing
                        self.counter -= 1
                    else:
                        self.type_map[tid] = folded_inner
                        
                    result.append(f"{base}<\033[1;36m[{tid}]\033[0m>")
                    i = j
                else:
                    result.append(type_str[i])
                    i += 1
            else:
                result.append(type_str[i])
                i += 1
        return "".join(result)

    def _flush_current_block(self):
        if self.current_block["main_error"]:
            self.all_blocks.append(self.current_block)
        self.current_block = {
            "main_error": None,
            "notes": [],
            "stack_trace": [],
            "raw_lines": []
        }

    def process_line(self, line):
        clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line).strip()
        if not clean_line: return

        # 1. 匹配主错误
        err_match = re.match(r'(.*?:\d+:\d+): error: (.*)', clean_line)
        if err_match:
            self._flush_current_block()
            self.current_block["main_error"] = {
                "loc": err_match.group(1),
                "msg": self._fold_type(err_match.group(2))
            }
            return

        # 2. 匹配 Note / Candidate 逻辑
        note_match = re.match(r'(.*?:\d+:\d+): note: (.*)', clean_line)
        if note_match and self.current_block["main_error"]:
            msg = note_match.group(2)
            # 提炼：如果是关于 candidate 转换失败的，直接提取出人话
            conv_match = re.search(r'no known conversion .*? from ‘(.*?)’ to ‘(.*?)’', msg)
            if conv_match:
                self.current_block["notes"].append({
                    "type": "conversion_fail",
                    "from": self._fold_type(conv_match.group(1)),
                    "to": self._fold_type(conv_match.group(2))
                })
            elif "candidate:" in msg:
                cand = msg.split("candidate:", 1)[1].strip()
                self.current_block["notes"].append({
                    "type": "candidate",
                    "func": self._fold_type(cand)
                })
            elif "declaration of" in msg:
                pass # 忽略无用的 declaration 废话
            else:
                self.current_block["notes"].append({"type": "raw", "msg": self._fold_type(msg)})
            return

        # 3. 匹配实例化堆栈 (In instantiation of / required from)
        if "In instantiation of" in clean_line or "required from" in clean_line:
            match = re.search(r'(.*?:\d+:\d+:|In file included from .*?:)\s*(.*)', clean_line)
            if match:
                self.current_block["stack_trace"].append({
                    "loc": match.group(1).replace('In file included from', '').strip(' :'),
                    "ctx": self._fold_type(match.group(2).replace('required from ', '').replace('In instantiation of ', ''))
                })
            return

        # 如果都不是，先暂存到 raw (可能是报错的代码切片，比如带有 ^ 的那行)
        if self.current_block["main_error"] and clean_line:
            self.current_block["raw_lines"].append(clean_line)

    def generate_human_report(self):
        self._flush_current_block()
        if not self.all_blocks:
            return ""

        report = []
        for i, block in enumerate(self.all_blocks):
            report.append(f"\033[91m{'='*60}\033[0m")
            report.append(f"\033[1;91m❌ ERROR {i+1}: \033[0m{block['main_error']['msg']}")
            report.append(f"\033[91m{'='*60}\033[0m\n")
            
            report.append(f"\033[1;93m📍 Location:\033[0m\n  {block['main_error']['loc']}")

            # 语义化提炼
            reason_generated = False
            for note in block["notes"]:
                if note["type"] == "conversion_fail":
                    report.append(f"\n\033[1;92m🤔 Human Translation (人话解释):\033[0m")
                    report.append(f"  You are trying to pass an argument of type:")
                    report.append(f"    👉 \033[1;35m{note['from']}\033[0m")
                    report.append(f"  But the receiving function/lambda expects:")
                    report.append(f"    👉 \033[1;35m{note['to']}\033[0m")
                    report.append(f"  \033[90m(Tip: This usually happens in std::visit when a variant contains a type your lambda doesn't handle.)\033[0m")
                    reason_generated = True
                    break
            
            if not reason_generated:
                # 把代码片段打出来
                code_snippet = "\n".join(block["raw_lines"][:2])
                if code_snippet:
                    report.append(f"\n\033[1;94m💻 Code Snippet:\033[0m\n  {code_snippet}")

            # 简化并反转的堆栈
            if block["stack_trace"]:
                report.append(f"\n\033[1;95m🥞 Template Call Stack (Top-down):\033[0m")
                # 倒序排列，让最外层调用在上面
                for idx, trace in enumerate(reversed(block["stack_trace"])):
                    report.append(f"  {idx+1}. {trace['loc']}")
                    report.append(f"     └─ {trace['ctx']}")

            report.append("\n")

        # 追加字典
        if self.type_map:
            report.append(f"\033[93m{'-'*60}\033[0m")
            report.append("\033[1;96m[ Template Dictionary (T1, T2...) ]\033[0m")
            for tid, content in self.type_map.items():
                report.append(f"  \033[1;36m[{tid}]\033[0m = {content}")
            report.append(f"\033[93m{'-'*60}\033[0m\n")

        return "\n".join(report)