from setuptools import setup

with open("README.md") as f:
    long_description = f.read()

setup(
    name="flowbio",
    version="0.8.0",
    description="A client for the Flow API.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/goodwright/flowbio",
    author="Flow.bio",
    author_email="engineering@flow.bio",
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: Internet :: WWW/HTTP",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    keywords="nextflow bioinformatics pipeline",
    packages=["flowbio", "flowbio.v2", "flowbio.cli"],
    entry_points={
        "console_scripts": [
            "flowbio = flowbio.cli:main",
        ],
    },
    python_requires=">=3.11",
    install_requires=[
        "tqdm",
        "kirjava",
        "requests",
        "httpx>=0.28,<1",
        "pydantic>=2,<3",
        "tenacity>=9,<10",
        "typing_extensions>=4.5",
    ]
)
