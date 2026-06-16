import os
import re

agents_dir = r"E:\se4cond agent\prism\agents"

# Mapping of file to its findings key
files_and_keys = {
    "bug_detector.py": ("bug_detector", "bug_findings"),
    "logic_auditor.py": ("logic_auditor", "logic_findings"),
    "security_scanner.py": ("security_scanner", "security_findings"),
    "style_checker.py": ("style_checker", "style_findings"),
}

for filename, (agent_name, findings_key) in files_and_keys.items():
    filepath = os.path.join(agents_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    pattern = re.compile(
        r"    for diff_file in pr_data\.diff_files:.*?    return \{\"" + findings_key + r"\": all_findings\}",
        re.DOTALL
    )
    
    replacement = f"""    combined_prompts = []
    for diff_file in pr_data.diff_files:
        if not diff_file.patch:
            continue
        context_str = ""
        if retriever and hasattr(retriever, "get_context"):
            context_str = await retriever.get_context(diff_file)
        
        combined_prompts.append(f"### File: {{diff_file.filename}}\\n\\n```diff\\n{{diff_file.patch}}\\n```\\n\\nContext:\\n{{context_str}}")

    if not combined_prompts:
        return {{"{findings_key}": []}}

    prompt = "## Pull Request Diffs\\n\\n" + "\\n\\n".join(combined_prompts)

    response = await llm.ainvoke(
        [
            {{"role": "system", "content": _SYSTEM_PROMPT}},
            {{"role": "user", "content": prompt}},
        ]
    )

    findings = _parse_findings(response.content, "{agent_name}")
    all_findings.extend(findings)

    logger.info(
        "{agent_name.replace('_', ' ').title()} found %d issues across %d files",
        len(all_findings),
        len(pr_data.diff_files),
    )
    return {{"{findings_key}": all_findings}}"""
    
    new_content = pattern.sub(replacement, content)
    
    if new_content != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Refactored {filename} successfully!")
    else:
        print(f"Failed to match regex for {filename}")
