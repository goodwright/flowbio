UPLOAD_SAMPLE = """mutation uploadDemultiplexedData(
  $blob: Upload! $isLastData: Boolean! $isLastSample: Boolean! $previousData: [ID]
  $expectedFileSize: Float! $data: ID $filename: String! $sampleName: String!
  $category: ID $organism: String $source: String $purificationTarget: String
  $scientist: String $pi: String $organisation: String $purificationAgent: String
  $experimentalMethod: String $condition: String $sequencer: String $comments: String
  $fivePrimeBarcodeSequence: String $threePrimeBarcodeSequence: String $threePrimeAdapterName: String
  $threePrimeAdapterSequence: String $read1Primer: String
  $read2Primer: String $rtPrimer: String $umiBarcodeSequence: String
  $umiSeparator: String $strandedness: String $rnaSelectionMethod: String
  $project: String $sourceText: String $purificationTargetText: String
  $geo: String $ena: String $pubmed: String
) { uploadDemultiplexedData(
  blob: $blob isLastData: $isLastData isLastSample: $isLastSample
  expectedFileSize: $expectedFileSize data: $data previousData: $previousData
  filename: $filename sampleName: $sampleName category: $category
  organism: $organism source: $source purificationTarget: $purificationTarget
  scientist: $scientist pi: $pi organisation: $organisation project: $project
  purificationAgent: $purificationAgent experimentalMethod: $experimentalMethod
  condition: $condition sequencer: $sequencer comments: $comments
  fivePrimeBarcodeSequence: $fivePrimeBarcodeSequence threePrimeBarcodeSequence: $threePrimeBarcodeSequence
  threePrimeAdapterName: $threePrimeAdapterName threePrimeAdapterSequence: $threePrimeAdapterSequence
  read1Primer: $read1Primer read2Primer: $read2Primer
  rtPrimer: $rtPrimer umiBarcodeSequence: $umiBarcodeSequence umiSeparator: $umiSeparator
  strandedness: $strandedness rnaSelectionMethod: $rnaSelectionMethod
  sourceText: $sourceText purificationTargetText: $purificationTargetText
  geo: $geo ena: $ena pubmed: $pubmed
) { dataId sampleId } }"""