# flowbio

A client for the Flow API.

```python
    
import flowbio

client = flowbio.Client()
client.login("your_username", "your_password")

# Upload standard data
data = client.upload_data("/path/to/file.fa", progress=True, retries=5)
print(data)

# Upload sample
sample = client.upload_sample(
    "My Sample Name",
    "/path/to/reads1.fastq.gz",
    "/path/to/reads2.fastq.gz", # optional
    progress=True,
    retries=5,
    metadata={
        "category": "RNA-Seq",
        "strandedness": "unstranded",
    }
)
print(sample)

# Upload multiplexed
multiplexed = client.upload_multiplexed(
    "/path/to/reads.fastq.gz",
    progress=True,
    retries=5,
)
print(multiplexed)

# Upload annotation
annotation = client.upload_annotation(
    "/path/to/annotation.csv",
    progress=True,
    retries=5,
)
print(annotation)

# Run pipeline
execution = client.run_pipeline(
    "RNA-Seq",
    "3.8.1",
    "23.04.3",
    params={"param1": "param2"},
    data_params={"fasta": 123456789},
)
```
