import flowbio

client = flowbio.Client("https://api.staging2.flow.bio/graphql")
client.login("sam", "michaelmas")

'''data = client.upload_annotation(
    "/Users/sam/Downloads/clip-samplesheet.csv"
)
print(data)

data = client.upload_multiplexed(
    "/Users/sam/Downloads/multiplexed.fastq.gz"
)
print(data)'''

sample = client.upload_sample(
    "Test sample",
    "/Users/sam/Downloads/war-horse.mkv",
    "/Users/sam/Downloads/kingdom-heaven.mkv",
    progress=True,
    retries=10
)
print(sample)

