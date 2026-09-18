// variable declarations: gets every element by it's unique ID
const goButton = document.getElementById('go-button')
const inputBar = document.getElementById('input-bar')
const inputBox = document.getElementById('input-box')
const singleOrList = document.getElementById('single-or-list')
const singleButton = document.getElementById('single-button')
const listButton = document.getElementById('list-button')
const csvCheck = document.getElementById('csv-check')
const csvCheckbox = document.getElementById('csv-checkbox')
const outputBox = document.getElementById('output-box')
const massOutput = document.getElementById('mass-output')
const learnMoreArrow = document.getElementById('learn-more-arrow')
const explanationModal = document.getElementById('explanation-modal')
const goBackButton = document.getElementById('go-back-button')
const introBox = document.getElementById('intro-box')
const closeIntro = document.getElementById('close-intro')
const beginTutorialButton = document.getElementById('begin-tutorial-button')
const sessionHistoryArrow = document.getElementById('session-history-arrow')
const sessionHistoryModal = document.getElementById('session-history-modal')
const bottomTaxonGraphic = document.getElementById('bottom-taxon-graphic')
const confidenceOutput = document.getElementById('confidence-output')
const confidenceText = document.getElementById('confidence-text')
const massText = document.getElementById('mass-text')



//handling session details (refreshing versus changing tabs)

const navEntries = performance.getEntriesByType("navigation");
const navigationType = navEntries.length > 0 ? navEntries[0].type : null;

if (navigationType === "reload") {
  sessionStorage.removeItem('introSeen');
  sessionStorage.removeItem('history');
}

if (sessionStorage.getItem('introSeen') === 'true') {
  introBox.classList.add('hidden');
  inputBox.classList.remove('hidden');
  bottomTaxonGraphic.classList.remove('hidden');
}

// function definitions

// The prediction service returns null (with a `warning`) when no rank of the
// taxonomy occurs in the training data.  Never call toFixed on those.
const NOT_PREDICTABLE = 'Not predictable: no rank of this taxonomy occurs in the training data'
const fmtGrams = (value) =>
  (value === null || value === undefined || Number.isNaN(value)) ? 'NA' : `${value.toFixed(2)} g`
const fmtCsv = (value) =>
  (value === null || value === undefined || Number.isNaN(value)) ? 'NA' : value.toFixed(2)

// makes output box visible and generates output based on input
const handleGoClick = async (event) => {
  inputBox.classList.add('moved')
  goButton.textContent = 'Go Again!'
  if (outputBox.classList.contains('hidden')) {
    outputBox.classList.toggle('hidden')
  }
  if (singleButton.classList.contains('clicked')) {
    learnMoreArrow.classList.remove('hidden')
    sessionHistoryArrow.classList.remove('hidden')
  }
  if (listButton.classList.contains('clicked')) {
    learnMoreArrow.classList.add('hidden')
    sessionHistoryArrow.classList.add('hidden')
  }
  
  // if the user clicks go without typing any input
  const userInput = inputBar.value.trim()
  if (!userInput) {
    massText.textContent = 'no input'
    confidenceText.textContent = 'no input'
    return
  }

  // while waiting for response
  massText.textContent = 'Checking species name...'
  confidenceText.textContent = 'Waiting for mass prediction...'

  // interacting with the microservice (prototype_lookup.py)
  try {

  let data

  if (singleButton.classList.contains('clicked')) {
    data = await myLookupMicroservice(userInput)
  } else {
    data = await myMultiLookupMicroservice(userInput)
  }

  if (data.status === 'success') {

    // single species
    if (singleButton.classList.contains('clicked')) {

      massText.textContent = `${data.message}`
      confidenceText.textContent = `${data.confidence}`

      addToSessionHistory(userInput, data.message)

    }

    // multiple species
    else {

      let massResults = ''
      let confidenceResults = ''

      data.results.forEach(item => {

        if (item.prediction === null) {
          massResults += `${item.taxonomy.species}: ${item.warning || NOT_PREDICTABLE};\n`
          confidenceResults += `${item.taxonomy.species}: NA;\n`
          return
        }

        massResults +=
          `${item.taxonomy.species}: ${fmtGrams(item.prediction)};\n`

        confidenceResults +=
          `${item.taxonomy.species}: ${fmtGrams(item.lower_bound)} - ${fmtGrams(item.upper_bound)};\n`

      })

      massText.textContent = massResults
      confidenceText.textContent = confidenceResults
      
      if (csvCheckbox.checked || data.results.length > 5) {

      massText.textContent = 'Output written to csv file'
      confidenceText.textContent = 'Output written to csv file'


  let csvContent =
    "Species,Predicted Mass (g),Lower Bound (g),Upper Bound (g)\n"

  data.results.forEach(item => {

    csvContent +=
      `"${item.taxonomy.species}",` +
      `${fmtCsv(item.prediction)},` +
      `${fmtCsv(item.lower_bound)},` +
      `${fmtCsv(item.upper_bound)}\n`

  })

  const blob = new Blob([csvContent], {
    type: "text/csv"
  })

  const url = URL.createObjectURL(blob)

  const link = document.createElement("a")

  link.href = url
  link.download = "taxonbodymassml_species_prediction.csv"

  document.body.appendChild(link)

  link.click()

  document.body.removeChild(link)

  URL.revokeObjectURL(url)
}
    }

  } else {

    massText.textContent = `${data.error}`
    confidenceText.textContent = 'Error'
  }

} catch (error) {

  console.error(error)

  massText.textContent = 'Error'
  confidenceText.textContent = 'Error'
}


}

 const addToSessionHistory = (input, output) => {
  let history = JSON.parse(sessionStorage.getItem('history')) || []
  history = history.filter(
    item => item.input.toLowerCase() !== input.toLowerCase()
  )

  history.unshift({ input, output })

  sessionStorage.setItem('history', JSON.stringify(history))
}

const renderSessionHistory = () => {
  const history = JSON.parse(sessionStorage.getItem('history')) || []

  sessionHistoryModal.innerHTML = "<p>Session History</p>"

  history.forEach(item => {
    const entry = document.createElement('div')
    entry.style.marginBottom = "10px"

    entry.innerHTML = `
      <strong>${item.input}</strong><br/>
      ${item.output}
    `

    sessionHistoryModal.appendChild(entry)
  })
}



// uses render to interact with the microservice
const myLookupMicroservice = async (query) => {

  const lookupURL =
    `https://look-up-service.onrender.com/single_species?species_name=${encodeURIComponent(query)}`

  try {
    const lookupResponse = await fetch(lookupURL)
    const lookupData = await lookupResponse.json()

    if (!lookupResponse.ok || !lookupData.taxonomy) {
      return {
        status: "error",
        error: lookupData.error || "Species not found"
      }
    }

    const rawTaxonomy = lookupData.taxonomy

if (rawTaxonomy.species === "UNK") {
  return {
    status: "error",
    error: "Species not found"
  }
}

    //making sure the order is correct
    const taxonomy = {
  	kingdom: rawTaxonomy.kingdom,
  	phylum: rawTaxonomy.phylum,
  	class: rawTaxonomy.class,
  	order: rawTaxonomy.order,
  	family: rawTaxonomy.family,
  	genus: rawTaxonomy.genus,
  	species: rawTaxonomy.species
    }

    console.log("Sending taxonomy:", taxonomy)

    const predictionURL = "https://purse-region-fresh-capabilities.trycloudflare.com/xgb_pred_single"

    const predictionResponse = await fetch(predictionURL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(taxonomy)
    })

    const predictionData = await predictionResponse.json()

    console.log("Prediction response:", predictionData)

    if (!predictionResponse.ok) {
  	return {
    	status: "error",
    	error: "Prediction failed"
  	}
    }

    if (predictionData.prediction === null) {
      return {
        status: "success",
        message: predictionData.warning || NOT_PREDICTABLE,
        confidence: "NA"
      }
    }

    return {
      status: "success",
      message: fmtGrams(predictionData.prediction),
      confidence: `${fmtGrams(predictionData.lower_bound)} - ${fmtGrams(predictionData.upper_bound)}`
    }

  }
  catch (error) {

    console.error("Network error:", error)

    return {
      status: "error",
      error: "Network error"
    }
  }
}

//for multi-species queries
const myMultiLookupMicroservice = async (query) => {

  const speciesList = query
    .split(/\n|,/)
    .map(item => item.trim())
    .filter(item => item.length > 0)

  try {
    const taxonomyList = []

    for (const species of speciesList) {

      const lookupURL =
        `https://look-up-service.onrender.com/single_species?species_name=${encodeURIComponent(species)}`

      const lookupResponse = await fetch(lookupURL)
      const lookupData = await lookupResponse.json()

      // skip invalid species
      if (!lookupResponse.ok || !lookupData.taxonomy) {
        console.log(`Skipping invalid species: ${species}`)
        continue
      }

      const rawTaxonomy = lookupData.taxonomy

if (rawTaxonomy.species === "UNK") {
  console.log(`Skipping unknown species: ${species}`)
  continue
}

      taxonomyList.push({
        kingdom: rawTaxonomy.kingdom,
        phylum: rawTaxonomy.phylum,
        class: rawTaxonomy.class,
        order: rawTaxonomy.order,
        family: rawTaxonomy.family,
        genus: rawTaxonomy.genus,
        species: rawTaxonomy.species
      })
    }

    // if everything failed
    if (taxonomyList.length === 0) {
      return {
        status: "error",
        error: "No valid species found"
      }
    }
    const response = await fetch(
      "https://purse-region-fresh-capabilities.trycloudflare.com/xgb_pred_multi",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(taxonomyList)
      }
    )

    const data = await response.json()

    if (!response.ok) {
      return {
        status: "error",
        error: "Prediction failed"
      }
    }
    return {
      status: "success",
      results: data.items
    }

  } catch (error) {

    console.error(error)

    return {
      status: "error",
      error: "Network error"
    }
  }
}

// reveals the csv checkbox
const handleListClick = (event) => {
  if (csvCheck.classList.contains('hidden')) {
    csvCheck.classList.toggle('hidden')
    inputBar.classList.remove('moved')
    goButton.classList.remove('moved')
    singleOrList.classList.remove('moved')
  }
  if (singleButton.classList.contains('clicked')) {
    singleButton.classList.remove('clicked')
  }
  if (!listButton.classList.contains('clicked')) {
    listButton.classList.add('clicked')
  }
}

// hides the csv check box
const handleSingleClick = (event) => {
  if (!csvCheck.classList.contains('hidden')) {
    csvCheck.classList.toggle('hidden')
    inputBar.classList.add('moved')
    goButton.classList.add('moved')
    singleOrList.classList.add('moved')

  }
  if (!singleButton.classList.contains('clicked')) {
    singleButton.classList.add('clicked')
  }
  if (listButton.classList.contains('clicked')) {
    listButton.classList.remove('clicked')
  }
}

// hides the input box and reveals the explanation modal
const handleLearnMoreClick = (event) => {
  outputBox.classList.add('moved')
  learnMoreArrow.classList.toggle('hidden')
  sessionHistoryArrow.classList.toggle('hidden')
  explanationModal.classList.toggle('hidden')
  inputBox.classList.add('hidden')
  goBackButton.classList.toggle('hidden')
}

const handleSessionHistoryClick = (event) => {
  renderSessionHistory() 
  outputBox.classList.add('moved')
  learnMoreArrow.classList.toggle('hidden')
  sessionHistoryArrow.classList.toggle('hidden')
  sessionHistoryModal.classList.toggle('hidden')
  inputBox.classList.add('hidden')
  goBackButton.classList.toggle('hidden')
}


// hides the explanation modal and reveals the input box
const handleGoBackClick = (event) => {
  goBackButton.classList.toggle('hidden')
  outputBox.classList.remove('moved')
  inputBox.classList.toggle('hidden')
  if (explanationModal.classList.contains('hidden')) {
	  sessionHistoryModal.classList.toggle('hidden')
  }
  else if (sessionHistoryModal.classList.contains('hidden')) {
  	explanationModal.classList.toggle('hidden')
  }
  learnMoreArrow.classList.toggle('hidden')
  sessionHistoryArrow.classList.toggle('hidden')
}

// hides the introduction modal
const handleCloseIntro = (event) => {
  introBox.classList.add('hidden')
  inputBox.classList.remove('hidden')
  beginTutorialButton.classList.remove('hidden')
  bottomTaxonGraphic.classList.remove('hidden')
  sessionStorage.setItem('introSeen', 'true')
}

const makeVisibilityIndependent = (event) => {
  if (introBox.classList.contains('hidden')) {
  	if (beginTutorialButton.classList.contains('hidden')) {
      		beginTutorialButton.classList.remove('hidden')
    	}
	if (inputBox.classList.contains('hidden')) {
      		inputBox.classList.remove('hidden')
    	}
  }
}

// event listener declarations: attaching all functions to their appropriate elements

goButton.addEventListener('click', handleGoClick)
inputBar.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') handleGoClick()
})

listButton.addEventListener('click', handleListClick)
singleButton.addEventListener('click', handleSingleClick)
learnMoreArrow.addEventListener('click', handleLearnMoreClick)
sessionHistoryArrow.addEventListener('click', handleSessionHistoryClick)
goBackButton.addEventListener('click', handleGoBackClick)
closeIntro.addEventListener('click', handleCloseIntro)
makeVisibilityIndependent()
