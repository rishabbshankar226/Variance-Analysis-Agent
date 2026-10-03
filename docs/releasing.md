# Release preparation

The version has one source: `src/variance_agent/version.py`. Hatch reads it for
package metadata; runtime and audit provenance import the same value. The current
development version is 0.3.0. No tag or registry publication is implied by merging.

1. Finish review, update CHANGELOG, and confirm all `Required checks` pass on the
   exact intended main commit. Review schema migration and input-contract changes.
2. Confirm version.py identifies the intended release and LICENSE matches the
   declared MIT metadata. Published schema files must retain their original shape.
3. Install `.[dev,excel,release]`; run tests, lint, compileall, and pip check.
4. Build into an empty directory using `python -m build --outdir dist`, then run
   `python -m twine check dist/*` and `python scripts/check_distribution.py dist`.
5. Install the wheel and sdist in separate clean environments. Run
   `python scripts/check_installation.py --without-excel` with each environment's
   interpreter. Both CLI examples and dependency-error behavior must pass.
6. Tag the already tested commit as `v<version>`. Prepare GitHub release notes
   containing the changelog, input/schema migrations, artifacts, their SHA-256
   checksums, and the tested commit. Publish only when a release is intended.

PyPI publishing is optional and is not configured. If selected later, use an
explicit project destination and scoped trusted publishing. Do not add reusable
credentials or live-model keys to test workflows. Release publication must not
be canceled by PR-build concurrency.
