---

## Features

{{totalFeatures features.categories}} capabilities across {{count features.categories}} categories.

{{#each features.categories}}
### {{this.name}}

{{#each this.items}}
- {{#if this.highlight}}**{{this.name}}**{{else}}{{this.name}}{{/if}}: {{this.description}}
{{/each}}

{{/each}}
