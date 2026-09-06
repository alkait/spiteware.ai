# Morning queue

One file per run: `queue/YYYY-MM-DD.md`. Each candidate is a block like this. Flip `status` to `approve`, `edit`, or `reject`, fix any copy, then run the merge step.

```
## FuturePost                              status: pending   score: 9/10
url:       https://futurepost.app/
replaces:  FutureMe · $9/yr   (source: https://...)
builder:   Ayush Soni (@mrayushsoni)
grudge:    "I've used FutureMe since I was 16. After the acquisition they added paid tiers."
           source: https://news.ycombinator.com/item?id=45744680
tagline:   Write a letter to your future self. Free forever, no ads, no premium tier waiting to ambush you.
tags:      letters, web, ios
vibe:      no
icon:      📬
why:       explicit grudge (3) · price verified (2) · solo (2) · one thing (1) · not vibe coded (0) · +1 title says "greed"
```

Merge moves `approve` blocks into `data/apps.json`, `reject` blocks into `data/rejected.json`, and leaves `pending` and `edit` blocks in place.
