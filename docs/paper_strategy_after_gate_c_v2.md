# Paper strategy after Gate C development v2

## Recommended framing

The defensible paper at this checkpoint is not yet a successful early-warning
system. Its strongest coherent story is a staged falsification result:

> Persona directions can encode persona expression, and a frozen pressure
> protocol can induce sustained output drift, yet the same activation monitor is
> not automatically a specific prospective predictor of that drift beyond the
> observable text prefix.

A working title is:

> **Representation Is Not Prediction: Stress-Testing Persona Vectors as Early
> Warning Signals for LLM Persona Drift**

This framing preserves the original Latent Persona Seismograph motivation while
making the failed specificity gate a central scientific result rather than
hiding it.

## Claims currently supported

- Held-out persona expression is linearly separable along independently extracted
  persona directions, with non-questionnaire behavior correlation (Gate B).
- The scoped cautious persona exhibits sustained transfer drift under both frozen
  pressure schedules and not under clean controls (Gate A).
- A causal pre-response forecasting benchmark can be constructed without current
  response or future-probe leakage.
- On the inspected development data, activation adds only a small and uncertain
  five-turn AUPRC increment over a strong same-prefix text model.
- A resistant persona axis shows strong activation alarms under pressure without
  sustained judged output drift, demonstrating representation/behavior
  dissociation and inadequate cross-axis specificity.

## Claims not supported

- A general cross-persona early-warning detector.
- A confirmatory positive incremental forecasting effect.
- A causal claim that the layer-20 activation change produces output drift.
- Intervention efficacy (RQ3); intervention should not be evaluated until a
  valid warning signal is established.

## Two scientifically valid routes

### Route A: build a stronger seismograph

Collect a new **development**, not confirmation, corpus with multiple susceptible
and resistant axes. Learn a pressure-residual representation using training axes,
select it on validation axes/topics, and reserve at least one entire axis plus new
topics as an untouched development test. Only after this succeeds should a
separate Qwen confirmation and frozen Llama replication be generated.

This route is more ambitious and expensive. It requires new persona-vector
extraction, multi-axis stress protocols, nested axis/topic splits, and a power
analysis before confirmation.

### Route B: confirm the dissociation

Freeze the present pipeline and collect new Qwen topics/seeds to test the
prediction that persona-vector activation responds to pressure but lacks
behavioral-drift specificity on resistant axes. Replicate the frozen analysis on
Llama-3.1-8B-Instruct. This yields a narrower but cleaner measurement paper and
avoids repeated development-test tuning.

## Recommendation

Use Route B as the minimum publishable path and treat Route A as an extension.
The immediate next protocol should preregister the dissociation, not claim a
positive seismograph. It should freeze:

1. new topics and seeds;
2. the existing five-turn causal label and TF-IDF comparator;
3. no further feature or layer selection;
4. a positive-axis incremental-effect interval;
5. resistant-axis pressure false-alarm rate as a co-primary outcome;
6. Qwen first and Llama replication second;
7. sample size from trajectory-level bootstrap simulations using the observed
   effect and variance, with a smallest effect of interest chosen substantively.

The intervention RQ should be removed from the first paper unless subsequent new
development data produces a specific warning signal.
