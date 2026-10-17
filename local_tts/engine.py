"""SLED-TTS 维语模型的推理封装（给 CLI 和本地 HTTP 服务共用）。"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "third_party" / "SLED-TTS"))

from transformers import AutoProcessor, RobertaTokenizer  # noqa: E402

from sled.sled import SpeechLlamaForCausalLM  # noqa: E402

SAMPLE_RATE = 24000
STRIDE = 320
BANDWIDTH = 6


class SledEngine:
    def __init__(
        self,
        model_dir: str | Path = ROOT / "models" / "sled-uyghur",
        encodec_dir: str | Path = ROOT / "models" / "encodec_24khz",
        device: str | None = None,
    ) -> None:
        self.device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )
        self.dtype = torch.float16 if self.device.type == "cuda" else torch.float32
        self.tokenizer = RobertaTokenizer.from_pretrained(str(model_dir))
        self.model = SpeechLlamaForCausalLM.from_pretrained(
            str(model_dir), torch_dtype=self.dtype, attn_implementation="sdpa"
        )
        self.model.initialize_codec(str(encodec_dir))
        self.model.to(self.device).eval()
        self.processor = AutoProcessor.from_pretrained(str(encodec_dir))
        self.lock = threading.Lock()
        self._ref_cache: dict[str, tuple[float, np.ndarray]] = {}

    def _load_ref(self, path: str | Path) -> np.ndarray:
        key = str(path)
        mtime = Path(path).stat().st_mtime
        cached = self._ref_cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        waveform, rate = sf.read(str(path), dtype="float32")
        if waveform.ndim == 2:
            waveform = waveform.mean(axis=1)
        if rate != SAMPLE_RATE:
            waveform = librosa.resample(waveform, orig_sr=rate, target_sr=SAMPLE_RATE)
        audio = np.asarray(waveform, dtype=np.float32)
        self._ref_cache[key] = (mtime, audio)
        return audio

    def synthesize(
        self,
        text: str,
        ref_audio: str | Path,
        ref_text: str,
        *,
        cfg: float = 1.5,
        min_seconds: float = 1.5,
        max_seconds: float = 8.0,
        seed: int | None = None,
    ) -> np.ndarray:
        text = (text or "").strip()
        ref_text = (ref_text or "").strip()
        if not text or not ref_text:
            raise ValueError("text 和 ref_text 都不能为空")

        audio = self._load_ref(ref_audio)
        encoded = self.tokenizer.batch_encode_plus(
            [ref_text + " " + text],
            add_special_tokens=True,
            padding="longest",
            truncation=True,
            return_tensors="pt",
        )
        input_ids = encoded["input_ids"].to(self.device)
        text_mask = encoded["attention_mask"].to(self.device)
        audio_inputs = self.processor(
            raw_audio=[audio], sampling_rate=SAMPLE_RATE, return_tensors="pt"
        )

        with self.lock, torch.inference_mode():
            if seed is not None:
                torch.manual_seed(seed)
            self.model.infer_cfg = float(cfg)
            self.model.min_speech_frames = int(float(min_seconds) * 75)
            codec_output = self.model.codec.encode(
                audio_inputs["input_values"].to(self.device),
                audio_inputs["padding_mask"].to(self.device),
                bandwidth=BANDWIDTH,
            )
            prompt_features = self.model.codec.quantizer.decode(
                codec_output.audio_codes[0].transpose(0, 1)
            )
            speech_mask = audio_inputs["padding_mask"][..., ::STRIDE].to(self.device)
            prompt_features = prompt_features.transpose(1, 2).to(self.model.dtype)
            prompt_frames = prompt_features.shape[1]
            attention_mask = torch.cat([text_mask, speech_mask], dim=1)
            max_length = min(
                self.model.config.max_position_embeddings,
                input_ids.shape[1] + prompt_frames + int(float(max_seconds) * 75),
            )
            _, generated = self.model.generate(
                input_ids=input_ids,
                inputs_embeds=prompt_features,
                attention_mask=attention_mask,
                max_length=max_length,
                do_sample=True,
                num_return_sequences=1,
            )
            decoded = self.model.codec.decoder(generated.transpose(-1, -2).float())
            output = decoded[0, 0, prompt_frames * STRIDE :].detach().float().cpu().numpy()

        return np.clip(output, -1.0, 1.0)
