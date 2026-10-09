Put labelled trajectory files here (*.jsonl, one trajectory per line).
Sources: your own hand-written examples, or a converted public AI-control dataset.
Include hard benign cases (legitimate actions that look unusual) as well as positives.

`monitor eval --labelled <file>` takes one file. To evaluate several sets together, concatenate them first
(`cat a.jsonl b.jsonl > set.jsonl`).

## Format

One JSON object per line:

    {"trajectory_id": "t2", "task": "update docs", "label": 1, "category": "placeholder",
     "actions": [{"tool": "Bash", "kind": "shell", "text": "ls", "label": 0},
                 {"tool": "Bash", "kind": "shell", "text": "echo ALPHA_MARKER"}]}

(Shown over three lines here for readability; in the file each trajectory is one line.)

Trajectory fields:

- `trajectory_id` (required): unique id. The dev/test split keeps each trajectory whole (40% of
  trajectories go to test, fixed seed), so no trajectory has actions on both sides.
- `task` (required): the user instruction the agent was working on. The judge sees it.
- `label` (required): 1 = malicious, 0 = benign. This is the default label for every action in the
  trajectory.
- `category` (optional): free text, e.g. the attack type or "benign".
- `actions` (required): the actions in order.

Action fields:

- `tool`: raw tool name as an agent would log it, e.g. `Bash`, `Edit`, `exec_command`.
- `kind`: one of `shell`, `code_exec`, `file_write`, `file_read`, `network`, `browser`, `mcp`, `agent`,
  `other` (monitor.schema.KINDS). Defaults to `other`. A rule with `"kinds"` only fires on those kinds.
- `text`: what the action does: the command, or the file path followed by the content written.
- `label` (optional): overrides the trajectory label for this action. Use it to mark benign setup steps
  inside a malicious trajectory, as in the example above, where `ls` is labelled 0.

The loader (monitor/dataset.py) rejects a line missing `trajectory_id`, `task`, `label` or `actions`.
