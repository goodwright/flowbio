SAMPLE = """query sample($id: ID!) {
  sample(id: $id) {
    id name private created category owner { id name username }
    initialData { id created data { id filename } } organism { id name }
    source { id name } purificationTarget { id name } project { id name }
    sourceText purificationTargetText threePrimeAdapterName
    scientist pi organisation purificationAgent experimentalMethod condition
    sequencer comments fivePrimeBarcodeSequence threePrimeBarcodeSequence 
    threePrimeAdapterSequence read1Primer read2Primer rtPrimer
    umiBarcodeSequence umiSeparator strandedness rnaSelectionMethod
    geo ena pubmed
  }
}"""