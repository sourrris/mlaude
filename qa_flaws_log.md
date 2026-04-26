# QA Agent Autonomous Flaws Log

- ~~The /help output listed '/toolsets', but executing the command resulted in 'Unknown command'. This suggests a discrepancy between the help documentation and the actual implemented commands.~~ **FIXED** — Added `_show_toolsets()` helper and `elif canonical == "toolsets":` dispatch branch in `cli.py`.
- ~~The initial /help output listed '/skills' under 'Tools & Skills', but executing the command resulted in 'Unknown command'. This indicates a significant discrepancy between the help documentation and the actual functionality of the tool.~~ **FIXED** — Added `_show_skills()` helper and `elif canonical == "skills":` dispatch branch in `cli.py`.
