# AquaGold UI Deploy Guard

This file is a non-negotiable project rule for every future AquaGold preview/release.

## The recurring regression we must never reintroduce
A deployment may render the page but leave Alpine navigation/buttons (`@click`) inactive. This has repeatedly happened after adding pre-Alpine DOM mutation layers.

## Hard rules
1. `main` / Production stays untouched until the isolated preview is explicitly approved.
2. Scripts injected before Alpine may wrap `window.app`, define helpers, and register state methods only.
3. Those scripts MUST NOT mutate the DOM at top level before Alpine finishes booting.
4. Never attach a page-wide `MutationObserver` to `document.documentElement`/`body` from a pre-Alpine layer.
5. Dynamic UI additions must run only after app initialization or after the relevant page/action is opened, preferably with native DOM/event handlers rather than re-initializing the whole Alpine tree.
6. Every active JavaScript file must pass `node --check`.
7. `tests/test_ui_stability_contract.py` must pass before a preview is considered deliverable.
8. A preview is not handed to the user unless login, dashboard navigation, customers, finance and smart-intake button bindings are considered the first smoke-test targets.
9. If a new UI layer causes dead buttons/blue screen/login stall, disable that newest UI layer first; do not patch main and do not stack another competing global controller on top.

## Current safe architecture
- Stable/base layers remain unchanged.
- `aqua-round6-user-fixes.js` is retained only for history/debugging and must NOT be injected.
- Active Round 6 UI is `aqua-round6-safe-ui.js`, which avoids top-level DOM mutation and global observers.
