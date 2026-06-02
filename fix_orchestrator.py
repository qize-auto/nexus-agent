with open("orchestration/orchestrator.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'memory_context = "' in line and i+1 < len(lines) and '".join([r.content for r in related[:3]])' in lines[i+1]:
        lines[i] = '                    memory_context = "\n".join([r.content for r in related[:3]])\n'
        lines[i+1] = ""
        print(f"OK: fixed memory_context at line {i+1}")
    
    if 'current_message = f"[相关记忆]' in line:
        j = i
        while j < len(lines) and '{message}"' not in lines[j]:
            j += 1
        if j < len(lines):
            new_line = '                    current_message = f"[相关记忆]\n{memory_context}\n\n[用户消息]\n{message}"\n'
            lines[i] = new_line
            for k in range(i+1, j+1):
                lines[k] = ""
            print(f"OK: fixed f-string at lines {i+1}-{j+1}")

with open("orchestration/orchestrator.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
print("Done")
