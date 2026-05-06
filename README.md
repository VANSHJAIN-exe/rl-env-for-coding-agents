# MEX

A reinforcement learning environment for training code-fixing agents. MEX provides a FastAPI server, async client, and an inference loop powered by OpenAI's API to generate unified diff patches that fix buggy Python code.

## Features

- **RL Environment Server**: FastAPI-based environment that manages episode state, resets, and step transitions
- **Async Client**: Type-safe HTTP client for communicating with the environment
- **OpenAI Integration**: Uses GPT models to generate code patches with fallback to predefined fixes
- **Patch Validation**: Unified diff format with structured action and observation models (Pydantic v2)
- **Task Grading**: Built-in task difficulty levels (easy, medium, hard) with reward scoring
- **Episode Tracking**: Full episode state management including step counts, total rewards, and best scores

## How It Works

Agents observe buggy code with line numbers and a bug description, then generate a unified diff patch as their action. The environment applies the patch, validates the output, and returns a reward. This loop trains agents to fix bugs autonomously.

## Requirements

- Python 3.9+
- FastAPI
- OpenAI API key (for inference)
- httpx (async HTTP client)
- Pydantic v2

See `requirements.txt` for dependencies.
