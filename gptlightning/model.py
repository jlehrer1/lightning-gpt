import torch
import torch.nn as nn
import torch.nn.functional as F


class SelfAttentionHead(nn.Module):
    def __init__(self, n_embd: int, head_size: int, context_length: int) -> None:
        super().__init__()

        self.key = nn.Linear(n_embd, head_size, bias=False)
        self.query = nn.Linear(n_embd, head_size, bias=False)
        self.value = nn.Linear(n_embd, head_size, bias=False)

        # dont register as attribute / in gradient graph
        self.register_buffer("tril", torch.tril(torch.ones(context_length, context_length)))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, T, C = x.shape
        k = self.key(x)
        q = self.query(x)

        # dont want to transpose along batch dim
        affinity = q @ k.transpose(-2, -1) * C ** (-0.5)

        # masking out "future values" in between each matmul
        # makes this a decoder block
        affinity = affinity.masked_fill(self.tril[:T, :T] == 0, float("-inf"))
        affinity = F.softmax(affinity, dim=-1)

        v = self.value(x)
        x = affinity @ v

        return x


class MultiHeadAttention(nn.Module):
    def __init__(self, n_heads: int, n_embd: int, head_size: int, context_length: int) -> None:
        super().__init__()

        self.heads = nn.ModuleList([SelfAttentionHead(n_embd, head_size, context_length) for _ in range(n_heads)])
        self.projection = nn.Linear(n_embd, n_embd)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # concat along channel dim of (B, T, C) Tensors
        x = torch.concat([head(x) for head in self.heads], dim=-1)
        x = self.projection(x)

        return x


class DecoderBlock(nn.Module):
    def __init__(self, n_heads: int, n_embd: int, context_length: int, dropout: float) -> None:
        super().__init__()
        head_size = n_embd // n_heads
        self.attention = MultiHeadAttention(n_heads, n_embd, head_size, context_length)

        # feedforward section
        # multiplier of 4 is recommended from attention is all you need paper
        # for inner matrix :shrug:
        self.ff = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.ReLU(),
            nn.Linear(4 * n_embd, n_embd),
            nn.Dropout(dropout),
        )

        # Layernorm for training stability
        self.ln1 = nn.LayerNorm(n_embd)
        self.ln2 = nn.LayerNorm(n_embd)

    def forward(self, x):
        x = x + self.attention(self.ln1(x))
        x = x + self.ff(self.ln2(x))

        return x


class GPTModel(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        n_blocks: int,
        n_heads: int,
        n_embd: int,
        context_length: int,
        dropout: float,
        tokenizer=None,
    ) -> None:
        super().__init__()
        self.vocab_size = vocab_size
        self.n_heads = n_heads
        self.n_embd = n_embd
        self.context_length = context_length

        self.token_embedding = nn.Embedding(vocab_size, n_embd)
        self.positional_embedding = nn.Embedding(context_length, n_embd)
        self.blocks = nn.Sequential(
            *[
                DecoderBlock(
                    n_embd=n_embd,
                    n_heads=n_heads,
                    context_length=context_length,
                    dropout=dropout,
                )
                for _ in range(n_blocks)
            ]
        )
        self.ln = nn.LayerNorm(n_embd)
        self.head = nn.Linear(n_embd, vocab_size)

        self.tokenizer = tokenizer

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, T = x.shape

        tok_emb = self.token_embedding(x)
        pos_emb = self.positional_embedding(torch.arange(T))
        x = tok_emb + pos_emb
        x = self.blocks(x)
        x = self.ln(x)
        logits = self.head(x)

        return logits

    def generate(self, prompt, max_new_tokens, context_length):
        if not torch.is_tensor(prompt):
            try:
                # cast to tensor and make a batch dim
                prompt = torch.tensor(self.tokenizer(prompt)).unsqueeze(0)
            except AttributeError:
                raise RuntimeError(
                    f"Prompt input is not tokenized and tokenizer was not provided to {self.__class__.__name__}. Either provide integer input or provide tokenizer to model initialization."
                )

        # prompt is (B, T) array of indices in the current context
        for _ in range(max_new_tokens):
            # crop prompt to the last context_length tokens
            prompt_cond = prompt[:, -context_length:]
            # get the predictions
            logits = self(prompt_cond)
            # focus only on the last time step
            logits = logits[:, -1, :]  # becomes (B, C)
            # apply softmax to get probabilities
            probs = F.softmax(logits, dim=-1)  # (B, C)
            # sample from the distribution
            prompt_next = torch.multinomial(probs, num_samples=1)  # (B, 1)
            # append sampled index to the running sequence
            prompt = torch.cat((prompt, prompt_next), dim=1)  # (B, T+1)

        if self.tokenizer is not None:
            # remove the batch dim for decoding
            prompt = self.tokenizer.decode(prompt.squeeze())

        return prompt
