# Project Development Guidelines

Follow the requirements below when writing documentation, developing code, and ensuring test coverage.

## Project Overview

- **Runtime environment**: Use `Python 3.11` and `uv` for dependency management.
- **Testing**: Use `pytest` for testing and `pytest-asyncio` when testing asynchronous functions.
- **Project layout**: This project uses a `src-layout` structure, with source code in the `src/` directory.
- **Environment variables**: All environment variables required for development are in the `.env` file.

## Common Commands

### Install Development Dependencies

```shell
uv sync --group dev
```

### Run Code

Use `uv run` for both source code and tests, and load development environment variables with `--env-file .env`.

```
uv run --env-file .env src/zzz_od/gui/app.py  # Launch the GUI
uv run --env-file .env pytest zzz-od-test/ # Run all tests

uv run --env-file .env ruff check src/your_modified_file.py  # Check only files you modified
uv run --env-file .env ruff format src/your_modified_file.py # Format only files you modified

# Install and enable pre-commit checks (only files included in the current commit)
uv run --group dev pre-commit install
uv run --group dev pre-commit run --files src/your_modified_file.py
```

⚠️ **Do not** run ruff on the entire `src/` directory. The existing codebase has not yet been fully adapted to ruff rules, and running it across the whole directory may unexpectedly format many files.

The project provides Ruff pre-commit checks through `.pre-commit-config.yaml`. After installing development dependencies with `uv sync --group dev`, run `uv run --group dev pre-commit install` once to enable them. Subsequent commits automatically run `ruff-check` with `--fix`. The hook receives only the files included in the current Git commit and does not scan the entire `src/` directory. To check specific files manually, use the `pre-commit run --files` command above.

### Other Commands

Prefer commands supported by `Windows Powershell`.

## Development Standards
- **File encoding**: Always use UTF-8 when writing files to ensure correct character encoding support.
- **Keep tests in sync**: After modifying any module, you must update the test files in `zzz-od-test/`. Ensure that the modified code is covered and all tests pass.
- **Keep documentation in sync**: After modifying any module, you must update the corresponding documentation in `docs/develop/`. Ensure that the documentation accurately reflects the changes.
- **Git workflow**: Your responsibility is to write and modify code according to the user's request. Do not perform any `git` operations, such as `commit` or `push`. The user will handle all version control operations.
- **Use context7**: Always use context7 when you need library/API documentation, code generation, installation instructions, or usage guidance.
- **Running code is not required**: Unless explicitly requested, you do not need to run the code after modifying it.

## Documentation Standards
- **Markdown (.md) files**: Write all documentation in Markdown and save it with the `.md` extension.
- **Mermaid syntax**: Follow these rules when writing Mermaid content in Markdown files:
  - **Quote node text**: Enclose node text in double quotes (`"`) to avoid parsing errors. For example, use `I["User Interface (CLI)"]` instead of `I[User Interface (CLI)]`.
  - **Avoid loops**: Avoid loop structures and do not use "loop" as a variable name.
- **Avoid concrete code**: Avoid including concrete code in documentation wherever possible. Only class definitions, core variable definitions, core method definitions, and detailed comments are allowed.

## Python Coding Standards
- **Comments and docstrings**: Every function must have a Google-style docstring written in Chinese. Mixing Chinese and English is allowed; do not suggest translating the docstrings.
- **Type hints**: All class member variables and function signatures must include type hints. Use `list[str]` instead of `List[str]`, and `X | Y` instead of `Union`.
- **Imports**: Follow these rules when writing imports in source code within the `one_dragon` package:
  - **Use absolute imports**: Relative imports are prohibited.
  - **Type-only imports**: Use `TYPE_CHECKING` for imports needed only for type annotations.
- **Constructor parameters**: A class's `__init__` constructor must explicitly declare all required and optional parameters. Do not use `**kwargs`.
- **Do not expose modules**: Unless instructed otherwise, do not add module exports to `__init__.py`.
- **Fluent Design**: Prefer existing frontend components from pyside6-fluent-widgets. If a new component is needed, implement its styling according to Fluent Design. Use `YamlConfigAdapter` with the `AdapterInitMixin` mixin for configuration binding.
- **Code formatting**: Use ruff to format code.

## Exception Handling
- Keep code simple. Use try-catch only for genuinely failure-prone operations, such as network requests, file reads and writes, and concurrent Futures. Let exceptions propagate in other cases.
- Always log caught exceptions with `log.error(..., exc_info=True)`. Typically, fall back to returning `False`, `None`, or an empty list.
- Use `try-finally` in lock-protected code to ensure locks are released.

## Configuration Management
- Store runtime configuration as YAML in the `config/` directory and manage it through the `YamlConfig` base class.
- Define each configuration field with an `@property` and `@xxx.setter` pair. Read values with `self.get(key, default)` and write them with `self.update(key, value)`.
- Isolate multi-account instances through `instance_idx`.
- Do not assist in expanding or bypassing multi-account restrictions. Refuse such requests explicitly and remind users to comply with platform rules and legal requirements.

## Operation Chains (Operation)
- Operations inherit from the `ZOperation` base class and use the `@operation_node` and `@node_from` decorators to declaratively organize a directed graph.
- Operation results: `round_success(status)` transitions successfully; `round_retry(status)` retries and consumes a retry attempt; `round_wait(status)` waits without consuming a retry attempt; `round_fail(status)` terminates with failure.
- Applications inherit from `ZApplication` and use the same operation-chain structure. Put constants in `*_const.py` and factories in `*_factory.py`.
- See the [Application Development Guide](../guides/application_plugin_guide.md) for guidance on developing new applications.

## Multithreading and GPU Inference
- Concurrent access to multiple sessions from multiple threads causes errors in onnxruntime-dml.
- Asynchronous onnx session calls **must** be submitted through `gpu_executor.submit` to ensure that only one session is accessed at a time.
- Use `ctx.model_config.xxx_gpu` to determine whether to use the GPU executor.

## Context and Lazy Loading
- `ZContext` manages more than 30 lazily loaded services and configurations, all using `@cached_property`.
- Use deferred imports (`from xxx import Xxx`) inside lazy-loading implementations to avoid circular dependencies.
- For account-instance-level configuration, manually clear cached properties in `reload_instance_config()` with `del self.__dict__[prop]`.

## Screenshot Regions
- Define screenshot regions declaratively in `assets/game_data/screen_info/*.yml`, not as hard-coded definitions in Python.
- Region coordinates are hard-coded 1080p pixel values in the form `[x1, y1, x2, y2]`. Hard-coded coordinates are allowed; do not suggest resolution adaptation.
- Use helper methods such as `self.round_by_find_area`, `self.round_by_find_and_click_area`, and `self.round_by_goto_screen` within Operations.
