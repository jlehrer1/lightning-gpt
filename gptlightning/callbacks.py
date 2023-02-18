import os

import torch
from pytorch_lightning.callbacks import Callback
import wandb

class SampleTextGenerationCallback(Callback):
    def __init__(
        self,
        context_length: int,
        write_path="./sample_output",
        every_n_epochs: int = 4,
        new_tokens=1000,
        log_wandb: bool = False,
    ) -> None:
        super().__init__()
        self.context_length = context_length
        self.write_path = write_path
        self.every_n_epochs = every_n_epochs
        self.new_tokens = new_tokens
        self.log_wandb = log_wandb
        
        if self.log_wandb:
            self.text_table = wandb.Table(columns=["epoch", "text"])
        os.makedirs(write_path, exist_ok=True)

    def on_validation_epoch_end(self, trainer: "pl.Trainer", pl_module: "pl.LightningModule") -> None:
        curr_epoch = pl_module.current_epoch

        if curr_epoch % self.every_n_epochs == 0:
            # generate writing sample just from "empty" prompt
            context = torch.zeros((1, 1), dtype=torch.long)
            text = pl_module.base_model.generate(
                context,
                max_new_tokens=self.new_tokens,
                context_length=self.context_length,
            )
            # just for writing purposes
            text = text.split(' ')

            with open(os.path.join(self.write_path, f"{curr_epoch}_sample_output.txt"), "w") as f:
                for idx, word in enumerate(text):
                    # write a newline every ten words to make the output 
                    # more human readable
                    if idx % 10 == 0:
                        f.write(f"{word} \n")
                    else:
                        f.write(f"{word} ")

            if self.log_wandb:
                self.text_table.add_data(curr_epoch, ' '.join(text[0: 100]))