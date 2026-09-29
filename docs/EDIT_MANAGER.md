# Global Edit Manager

`window.EditManager` is the central, page-agnostic editor state manager used by Materiel. It lives in `static/js/edit-manager.js` and is loaded by `base.html` before page scripts.

## Automatic DOM provider

The built-in `dom` provider tracks `input`, `select`, `textarea`, and `contenteditable` controls that represent editable state; form method is not used to decide whether a field is editable. Search/filter controls are ignored. Use:

- `data-em-ignore` to exclude a subtree or field.
- `data-em-track="name"` to opt a field outside a form into tracking.
- `data-em-native-undo` when a control must keep the browser's native Ctrl+Z behavior.
- `data-em-root` to limit automatic tracking to a specific DOM scope.

Checkboxes, radio groups, multiple selects, `Set`, `Map`, and `Date` values are supported by the codec. Dynamic select chains are restored up to three passes with `input`/`change` events so existing page logic can rebuild dependent options. Search/filter controls are excluded by semantic names or `data-em-ignore`.

## Dynamic providers

Use `register` when a page has state that is not represented by form controls:

```js
const unregister = EditManager.register('table', {
  label: 'جدول العمليات',
  capture: () => ({rows: [...rows], selected: new Set(selected)}),
  restore: state => { rows = [...state.rows]; selected = new Set(state.selected); render(); }
});
```

Call `commit('تعديل الجدول')` after a programmatic state change when it is not caused by a tracked DOM event.

## API writes

For an API operation that changes persistent data, use a compensating undo operation:

```js
await EditManager.execute({
  label: 'إضافة عملية',
  do: () => createOperation(),
  undo: () => deleteCreatedOperation(),
  redo: () => createOperationAgain()
});
```

API commands submitted through `execute` are serialized. Undo/redo failures put the command back in its original history position and show an error toast.

## Saving

Saving is deterministic:

1. `setSaveHandler(fn)` is used when a page owns an explicit save workflow.
2. Modified registered providers with a `save` function are saved.
3. Otherwise exactly one modified form is submitted with `requestSubmit()`.

If more than one form has unsaved changes, the manager refuses to guess and identifies the forms. HTML validation runs before submission. For pages that call `fetch()` from `submit` handlers, the manager associates the first non-GET request with the submitting form for 1500 ms and only marks that form clean after a successful response. A JSON `{ok:false}` response is treated as a failed save.

A normal POST navigation marks only that form's state as saved; changes in other forms remain dirty. Custom `fetch()` saves are associated with the submitting form and awaited by the manager; no arbitrary 20ms completion delay is used.

## History and dirty state

The baseline is captured after page load settles. History is limited to 100 steps and consecutive field edits are grouped with a 400 ms debounce. Dirty state is a comparison with the last saved baseline, so undoing all the way back to the saved state makes the page clean again.

The toolbar emits `edit-manager:change` with the current state and exposes `emStatus` as `clean`, `dirty`, or `saving`.

## Keyboard shortcuts

- Ctrl/Cmd+S: save
- Ctrl/Cmd+Z: undo
- Ctrl/Cmd+Y or Ctrl/Cmd+Shift+Z: redo

## Known limits

API undo is compensating business logic supplied by the page; the manager cannot infer how a database mutation should be reversed. A full page reload intentionally clears the in-memory history. Pages with complex non-form state should register that state explicitly rather than relying on DOM discovery.
