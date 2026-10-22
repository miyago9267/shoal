# Style

* Pure functions, standard library only, no global state.
* Bad arguments raise `ValueError` (wrong value) or `TypeError` (wrong type);
  never return a silent default for garbage input.
* Public functions have a docstring that states the contract in one or two
  sentences. A `TODO(fix)` comment is the spec for work not done yet: when the
  behaviour is implemented, delete the comment.
* Helpers that build on a public function must keep working unchanged when
  that function is fixed.
* Tests: one file per module under `tests/`, plain `unittest`.
