"""GraphQL mutations."""

UPLOAD_DATA = """mutation uploadData(
    $blob: Upload! $isLast: Boolean! $expectedFileSize: Float! $data: ID
    $filename: String!
) { uploadData(
    blob: $blob isLast: $isLast expectedFileSize: $expectedFileSize
    data: $data filename: $filename
) { dataId } }"""


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


UPLOAD_ANNOTATION = """mutation uploadAnnotationData(
    $blob: Upload! $isLast: Boolean! $expectedFileSize: Float! $data: ID
    $filename: String! $laneName: String $lane: ID $ignoreWarnings: Boolean
) { uploadAnnotationData(
    blob: $blob isLast: $isLast expectedFileSize: $expectedFileSize data: $data
    filename: $filename laneName: $laneName lane: $lane
    ignoreWarnings: $ignoreWarnings
) { dataId laneId } }"""


UPLOAD_MULTIPLEXED = """mutation uploadMultiplexedData(
    $blob: Upload! $isLast: Boolean! $expectedFileSize: Float! $data: ID
    $filename: String! $lane: ID $laneName: String
) { uploadMultiplexedData(
    blob: $blob isLast: $isLast expectedFileSize: $expectedFileSize data: $data
    filename: $filename lane: $lane laneName: $laneName
) { dataId } }"""