"""None voice provider — returns profile only, no audio generation."""


class NoneProvider:
    async def synthesize(self, text: str, profile: dict, output_path: str, **kwargs) -> str:
        raise RuntimeError("No voice provider configured. Set voice.provider in config.yaml.")
