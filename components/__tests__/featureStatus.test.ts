import { describe, expect, it } from 'vitest';

import { getFeatureStatusStyle } from '../featureStatus';

describe('getFeatureStatusStyle', () => {
  it('maps feature states to semantic status tokens', () => {
    expect(getFeatureStatusStyle('done')).toMatchObject({
      color: 'bg-success/10 text-success-foreground',
      dot: 'bg-success',
    });
    expect(getFeatureStatusStyle('in-progress')).toMatchObject({
      color: 'bg-info/10 text-info-foreground',
      dot: 'bg-info',
    });
    expect(getFeatureStatusStyle('backlog')).toMatchObject({
      color: 'bg-surface-muted text-muted-foreground',
      dot: 'bg-disabled-foreground',
    });
  });
});
