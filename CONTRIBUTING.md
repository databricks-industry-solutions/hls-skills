# Contributing

Thanks for contributing to HLS Skills.

### Contributor License Agreement (CLA)

By submitting a contribution to this repository, you certify that:

1. **You have the right to submit the contribution.**  
   You created the content yourself, or you have the right to submit it under the project's license.

2. **You grant us a license to use your contribution.**  
   Your contribution will be licensed under the same terms as the rest of this project, and you grant the project maintainers the right to use, modify, and distribute it as part of the project.

3. **You are not submitting confidential or proprietary information.**  
   Your contribution does not include anything you don’t have permission to share publicly.

If you are contributing on behalf of an organization, you confirm that you have the authority to do so. You agree to confirm these terms in your pull request. Any request that does not explicitly accept the terms will be assumed to have accepted.

## Adding or updating a skill

1. Follow [AGENTS.md](AGENTS.md) for guidelines on authoring and testing skills.
2. Consider starting from the appropriate `templates/`. See guidance in [AGENTS.md](AGENTS.md)
3. Put the skill at `skills/<category>/<skill-name>/SKILL.md`.
4. Folder name must match frontmatter `name`.
5. Update the skill table in `README.md`.
6. Push to a new branch names feat/skill_name then open a PR and request a second-party review.
