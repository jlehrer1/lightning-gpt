from functools import partial
from typing import Type, Union

import pytorch_lightning as pl
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoTokenizer

from gptlightning.metrics import Metrics
from gptlightning.model import GPTModel


class GPT(pl.LightningModule):
    def __init__(
        self,
        optimizer: Union[Type[nn.Module], partial(nn.Module)],
        scheduler: Union[Type[nn.Module], partial(nn.Module)] = None,
        vocab_size: int = 50304,
        n_blocks: int = 6,
        n_heads: int = 4,
        n_embd: int = 64,
        context_length: int = 64,
        dropout: float = 0.0,
        tokenizer: AutoTokenizer = None,
        metrics: Metrics = None,
    ) -> None:
        super().__init__()

        assert n_embd % n_heads == 0, "Embedding dim must be divisible by number of heads"

        self.save_hyperparameters()

        self.optimizer = optimizer
        self.scheduler = scheduler
        self.tokenizer = tokenizer

        self.base_model = GPTModel(
            vocab_size=vocab_size,
            n_blocks=n_blocks,
            n_heads=n_heads,
            n_embd=n_embd,
            context_length=context_length,
            dropout=dropout,
            tokenizer=tokenizer,
        )

        self.metrics = metrics

    def forward(self, x):
        return self.base_model(x)

    def _step(self, batch: torch.Tensor, phase: str, log_every_n_steps: int) -> float:
        x, y = batch
        logits = self(x)
        B, T, C = logits.shape
        logits = logits.view(B * T, C)
        targets = y.view(B * T)

        if self.metrics:
            result = self.metrics.compute_step(phase=phase, preds=logits, targets=targets, log_every_n_steps=log_every_n_steps)
            if result is not None:
                self.logger.log_metrics(result)

        loss = F.cross_entropy(logits, targets)
        self.log(f"{phase}_loss", loss, on_step=True, on_epoch=True)

        return loss

    def training_step(self, batch: torch.Tensor, batch_idx: int) -> float:
        loss = self._step(batch, "train", self.trainer.log_every_n_steps)

        return loss

    def validation_step(self, batch: torch.Tensor, batch_idx: int) -> float:
        loss = self._step(batch, "train", self.trainer.log_every_n_steps)

        return loss

    def configure_optimizers(self):
        optims = {}
        optimizer = self.optimizer(self.parameters())
        optims["optimizer"] = optimizer

        if self.scheduler is not None:
            scheduler = scheduler(optimizer)
            optims["scheduler"] = scheduler

        return optims

    def on_train_epoch_end(self) -> None:
        if self.metrics:
            result = self.metrics.compute_epoch("train")
            self.logger.log_metrics(result)

    def on_validation_epoch_end(self) -> None:
        if self.metrics:
            result = self.metrics.compute_epoch("val")
            self.logger.log_metrics(result)