from functools import partial

import pytorch_lightning as pl
import torch
from pytorch_lightning.loggers import WandbLogger
from torch.optim import Adam
from torch.utils.data import DataLoader
from transformers import AutoTokenizer

from gptlightning import SampleTextGenerationCallback
from gptlightning.data import AutoRegressiveTextSampler
from gptlightning.lightning_model import GPT

context_length = 128
batch_size = 16
num_workers = 8

device = "gpu" if torch.cuda.is_available() else None

# Text file containing all text you want to train on
with open("training_data.txt") as f:
    traintext = f.read()

# Text file containing all validation data
with open("validation_data.txt") as f:
    valtext = f.read()

print("Splitting text")
traintext = traintext.split(" ")
valtext = valtext.split(" ")

print("Generating tokenizer")
tokenizer = AutoTokenizer.from_pretrained("gpt2")

print("Setting up datasets")
traindata = AutoRegressiveTextSampler(
    text=traintext,
    context_length=context_length,
    tokenizer=tokenizer,
)

valdata = AutoRegressiveTextSampler(
    text=valtext,
    context_length=context_length,
    tokenizer=tokenizer,
)

trainloader = DataLoader(traindata, batch_size=batch_size, num_workers=num_workers)
valloader = DataLoader(valdata, batch_size=batch_size, num_workers=num_workers)

print("Setting up model")
model = GPT(
    optimizer=partial(
        Adam,
        lr=3e-4,
    ),
    vocab_size=tokenizer.vocab_size,
    tokenizer=tokenizer,
    context_length=context_length,
)

trainer = pl.Trainer(
    accelerator=device,
    devices=1 if device == "gpu" else None,
    max_epochs=500,
    logger=WandbLogger(name="GPT First Pass", project="Language Modeling"),
    callbacks=[SampleTextGenerationCallback(every_n_epochs=1, context_length=context_length, log_wandb=True)],
)

print("Beginning training phase")
trainer.fit(model, trainloader, valloader)
