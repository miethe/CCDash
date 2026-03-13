---

## Screenshots

{{#each (screenshotsByCategory screenshots.screenshots "readme")}}
### {{this.alt}}

![{{this.alt}}]({{this.file}})

{{/each}}
{{#unless (screenshotsByCategory screenshots.screenshots "readme")}}
> Screenshots coming soon. Run the dev server (`npm run dev`) to see CCDash in action.
{{/unless}}
