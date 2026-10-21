"""Unsloth 2x-Fast DPO Training Script for Llama-3-8B.

Enables memory-efficient QLoRA/LoRA Direct Preference Optimization on a single
consumer or cloud GPU (e.g., RTX 3090/4090, T4, A10G, A100).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def run_unsloth_dpo(
    data_path: Path,
    model_name: str = "unsloth/llama-3-8b-Instruct-bnb-4bit",
    output_dir: str = "./unsloth_dpo_aligned",
    max_seq_length: int = 2048,
    dry_run: bool = False,
) -> None:
    """Execute memory-optimized DPO alignment using Unsloth FastLanguageModel."""
    print("=================================================================")
    print("           UNSLOTH 2X-FAST DPO TRAINING RUNNER                   ")
    print("=================================================================")
    print(f"Target Model   : {model_name}")
    print(f"Dataset Source : {data_path}")
    print(f"Output Dir     : {output_dir}")

    if not data_path.exists():
        print(f"Error: Dataset {data_path} not found.")
        sys.exit(1)

    with open(data_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    print(f"Loaded {len(records)} curated, length-matched DPO pairs.")

    if dry_run:
        print("\n[Dry Run Active] Skipping GPU allocation and gradient descent.")
        print("Dataset successfully verified and ready for Unsloth training.")
        return

    try:
        from datasets import Dataset  # type: ignore
        from trl import DPOConfig, DPOTrainer  # type: ignore
        from unsloth import FastLanguageModel, PatchDPOTrainer  # type: ignore
    except ImportError as e:
        print("\n[Notice: Unsloth ML Dependencies Required for GPU Fine-Tuning]")
        print(f"Missing dependency: {e.name}")
        print("To install Unsloth on CUDA workstations/clusters:")
        print("  pip install \"unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git\"")
        print("  pip install --no-deps trl peft accelerate bitsandbytes\n")
        return

    # 1. Patch DPOTrainer with Unsloth memory optimizations
    PatchDPOTrainer()

    # 2. Load 4-bit quantized base model
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_length,
        load_in_4bit=True,
    )

    # 3. Add LoRA Adapters
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # 4. Prepare dataset
    hf_dataset = Dataset.from_dict({
        "prompt": [r["prompt"] for r in records],
        "chosen": [r["chosen"] for r in records],
        "rejected": [r["rejected"] for r in records],
    })

    # 5. DPO Hyperparameters
    dpo_args = DPOConfig(
        output_dir=output_dir,
        beta=0.1,
        learning_rate=5e-7,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=16,
        num_train_epochs=3,
        logging_steps=1,
        save_strategy="epoch",
        fp16=False,
        bf16=True,
    )

    trainer = DPOTrainer(
        model=model,
        ref_model=None,
        args=dpo_args,
        beta=0.1,
        train_dataset=hf_dataset,
        tokenizer=tokenizer,
        max_length=max_seq_length,
        max_prompt_length=1024,
    )

    print("\nLaunching Unsloth DPO Training...")
    trainer.train()
    model.save_pretrained_merged(output_dir, tokenizer, save_method="merged_16bit")
    print(f"Alignment complete. Merged weights saved to: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Unsloth DPO training runner.")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(__file__).parent / "data" / "dpo_expanded.jsonl",
        help="Path to curated DPO pairs JSONL.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="unsloth/llama-3-8b-Instruct-bnb-4bit",
        help="Base model ID.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test dataset loading without allocating GPU memory.",
    )
    args = parser.parse_args()
    run_unsloth_dpo(args.data, model_name=args.model, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
