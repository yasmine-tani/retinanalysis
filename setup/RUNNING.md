# Running RetinAnalysis (after setup is already done)

```
conda activate retinanalysis
cd retinanalysis
jupyter lab
```

## Getting updates

```
cd retinanalysis
git pull
```

If `pip install`-level dependencies changed (rare — you'll know because `import retinanalysis` starts erroring), re-run from an activated environment:

```
pip install -e .
```
