# Contributing to Aegra

Thank you for your interest in contributing to Aegra! 🎉

Aegra is an open source LangGraph Platform alternative, and we welcome all contributions - from bug reports to feature implementations.

## 🚀 Quick Start for Contributors

### Development Setup

1. **Fork and Clone**

   ```bash
   git clone https://github.com/YOUR_USERNAME/aegra.git
   cd aegra
   ```

2. **Environment Setup**

   ```bash
   # Install dependencies
   uv install

   # Activate virtual environment
   source .venv/bin/activate  # Mac/Linux
   # OR .venv/Scripts/activate  # Windows

   # Copy environment file
   cp .env.example .env
   ```

3. **Database Setup**

   ```bash
   # Start PostgreSQL
   docker-compose up -d postgres

   # Run migrations
   alembic upgrade head
   ```

4. **Run Tests**

   ```bash
   pytest
   ```

5. **Start Development Server**
   ```bash
   python run_server.py
   ```

## 🎯 How to Contribute

### 🐛 Reporting Bugs

Found a bug? Help us fix it!

1. Check if the issue already exists in our [issue tracker](https://github.com/ibbybuilds/aegra/issues)
2. If not, [create a new issue](https://github.com/ibbybuilds/aegra/issues/new) with:
   - Clear description of the problem
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (Python version, OS, etc.)
   - Relevant logs or error messages

### 💡 Suggesting Features

Have an idea for Aegra? We'd love to hear it!

1. Check our [roadmap](README.md#roadmap) and existing issues
2. [Open a feature request](https://github.com/ibbybuilds/aegra/issues/new) with:
   - Clear description of the feature
   - Use case and benefits
   - Proposed implementation approach (if you have ideas)

### 🔧 Code Contributions

#### Good First Issues

New to the project? Look for issues labeled [`good first issue`](https://github.com/ibbybuilds/aegra/labels/good%20first%20issue).

#### Priority Areas

We especially welcome contributions in:

- **Agent Protocol Compliance**: Improving spec alignment
- **Authentication**: Adding JWT, OAuth, custom auth backends
- **Deployment**: Docker, Kubernetes, cloud deployment guides
- **Testing**: Unit tests, integration tests, end-to-end tests
- **Documentation**: API docs, tutorials, examples
- **Performance**: Optimization and benchmarking

#### Pull Request Process

1. **Create a Branch**

   ```bash
   git checkout -b feature/your-feature-name
   # OR
   git checkout -b fix/issue-description
   ```

2. **Make Changes**

   - Write clean, documented code
   - Follow existing code style
   - Add tests for new functionality
   - Update documentation if needed

3. **Test Locally**

   ```bash
   # Run tests
   pytest

   # Run linting (if configured)
   # black . && isort . && flake8

   # Test the server manually
   python run_server.py
   curl http://localhost:8000/health
   ```

4. **Commit Changes**

   ```bash
   git add .
   git commit -m "feat: add awesome new feature"

   # Use conventional commits format:
   # feat: new feature
   # fix: bug fix
   # docs: documentation changes
   # test: test additions/modifications
   # refactor: code refactoring
   # chore: maintenance tasks
   ```

5. **Push and Create PR**

   ```bash
   git push origin your-branch-name
   ```

   Then create a pull request on GitHub with:

   - Clear title and description
   - Reference any related issues
   - Explain what changed and why

## 📋 Development Guidelines

### Code Style

- Follow Python PEP 8 conventions
- Use type hints where possible
- Write descriptive docstrings for functions and classes
- Keep functions focused and reasonably sized

### Testing

- Write tests for new features and bug fixes
- Use pytest for testing framework
- Include both unit tests and integration tests
- Test both success and error scenarios

### Documentation

- Update README.md if adding user-facing features
- Add docstrings to new functions and classes
- Update API documentation if changing endpoints
- Include examples for complex features

### Database Changes

- Create Alembic migrations for schema changes
- Test migrations both up and down
- Include sample data if helpful

## 🏗️ Project Structure

```
aegra/
├── src/agent_server/     # Main application code
│   ├── core/            # Database, config, infrastructure
│   ├── models/          # Pydantic models and schemas
│   ├── services/        # Business logic
│   └── utils/           # Helper functions
├── graphs/              # Example agent graphs
├── tests/               # Test suite
├── docs/                # Documentation
├── deployments/         # Docker and deployment configs
└── alembic/            # Database migrations
```

## 🆘 Getting Help

- **Questions**: Open a [discussion](https://github.com/ibbybuilds/aegra/discussions)
- **Chat**: Join our community (coming soon!)
- **Documentation**: Check the [README](README.md) and [docs](docs/)

## 🎖️ Recognition

Contributors will be:

- Listed in our README
- Mentioned in release notes for significant contributions
- Invited to join our core contributor team (for regular contributors)

## 📄 License

By contributing to Aegra, you agree that your contributions will be licensed under the Apache 2.0 License.

---

**Thank you for helping make Aegra the best open source LangGraph Platform alternative!** 🚀

_Questions? Feel free to ask in issues or discussions. We're here to help!_
