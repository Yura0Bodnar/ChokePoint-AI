## Summary

<!-- What does this PR do, in 2-3 sentences? -->

## Which architecture sections does this implement?

<!-- e.g. ARCHITECTURE_AND_PLAN.md §6 Data Contracts, §9 API Surface -->

## Self-verification output

<!-- Paste the output of the self-verification commands from your PROMPT_*.md file. -->

```
$ uv run ruff check . && uv run ruff format --check .


$ uv run mypy ...


$ uv run pytest -m "not live" ...


```

## Checklist

- [ ] I read the relevant section(s) of `ARCHITECTURE_AND_PLAN.md` before starting
- [ ] I did not touch files outside my ownership map (see architecture §11.1) without review
- [ ] `contracts.py` was not modified, or was modified with the whole team's sign-off
- [ ] No secrets, `.env`, or Terraform artifacts are in this diff
- [ ] CI is green on this PR
