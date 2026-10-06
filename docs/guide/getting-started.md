# Getting started

## Add the skills to Genie Code

1. Clone the [hls-skills repository](https://github.com/databricks-industry-solutions/hls-skills) into your Databricks workspace as a Git folder.
2. Open Genie Code and select **Customizations**.
3. Add the cloned folder, pointing it at the `skills` subfolder.

Genie Code now picks a skill when your request matches the skill's description.

## Optional: sync the skills to Unity Catalog

[Unity Catalog skills](https://docs.databricks.com/aws/en/agents/uc-skills/) make the skills available through Unity Gateway. The repository includes `sync_skills_git2unity.py` to publish them.

1. Start serverless compute or a cluster on Databricks Runtime 15.0 or above.
2. Open the [web terminal](https://docs.databricks.com/aws/en/compute/web-terminal#launch-the-web-terminal). It comes with the [Databricks CLI](https://docs.databricks.com/aws/en/compute/web-terminal#run-databricks-cli-commands) installed.
3. From the repository root, list the skills that would be published:

    ```bash
    uv run sync_skills_git2unity.py --dry-run
    ```

4. Publish or update the skills:

    ```bash
    uv run sync_skills_git2unity.py --catalog <your_catalog> --schema <your_schema> --warehouse-id <your_sql_wh>
    ```

    To find the warehouse ID, go to **SQL Warehouses** in the left menu and select the warehouse.

!!! note
    A skill's `tests/` and `eval/` folders are never published by the sync script. They stay in Git for contributors.

## Use the skills with other agents

The skills follow the [Agent Skills](https://agentskills.io/specification) standard, so agents that support it can load the same folders. For example, copy a skill folder into `.claude/skills/` to use it with Claude Code.
