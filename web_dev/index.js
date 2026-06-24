// variable declarations: gets every element by it's unique ID
const goButton = document.getElementById('go-button')
const inputBar = document.getElementById('input-bar')
const inputBox = document.getElementById('input-box')
const singleOrList = document.getElementById('single-or-list')
const singleButton = document.getElementById('single-button')
const listButton = document.getElementById('list-button')
const csvCheck = document.getElementById('csv-check')
const outputBox = document.getElementById('output-box')
const massOutput = document.getElementById('mass-output')
const learnMoreArrow = document.getElementById('learn-more-arrow')
const explanationModal = document.getElementById('explanation-modal')
const goBackButton = document.getElementById('go-back-button')
const introBox = document.getElementById('intro-box')
const closeIntro = document.getElementById('close-intro')
const beginTutorialButton = document.getElementById('begin-tutorial-button')
const API_BASE =
  window.TAXON_CONFIG?.API_BASE_URL ||
  'https://haileystaxonbodymassml.onrender.com'

//handling session details (refreshing versus changing tabs)

const navigationType = performance.getEntriesByType("navigation")[0].type;

if (navigationType === "reload") {
  sessionStorage.removeItem('introSeen');
}

if (sessionStorage.getItem('introSeen') === 'true') {
  introBox.classList.add('hidden');
  inputBox.classList.remove('hidden');
}

// function definitions

// makes output box visible and generates output based on input
const handleGoClick = async (event) => {
  inputBox.classList.add('moved')
  goButton.textContent = 'Go Again!'
  if (outputBox.classList.contains('hidden')) {
    outputBox.classList.toggle('hidden')
  }
  if (singleButton.classList.contains('clicked')) {
    learnMoreArrow.classList.remove('hidden')
  }
  if (listButton.classList.contains('clicked')) {
    learnMoreArrow.classList.add('hidden')
  }
  
  // if the user clicks go without typing any input
  const userInput = inputBar.value.trim()
  if (!userInput) {
    massOutput.textContent = 'no input'
    return
  }

  // while waiting for response
  massOutput.textContent = 'Checking species name...'

  // interacting with the microservice (prototype_lookup.py)
  try {
    const data = await myLookupMicroservice(userInput)

    if (data.status === 'success') {
      massOutput.textContent = `success: ${data.message}`
    } else {
      massOutput.textContent = `not success: ${data.error}`
    }
  } catch (error) {
    console.error(error)
    massOutput.textContent = 'Error'
  }
}

// uses render to interact with the microservice
const myLookupMicroservice = async (query) => {
  const url = `${API_BASE}/single_species?species_name=${encodeURIComponent(query)}`

  try {
    const response = await fetch(url)
    const data = await response.json()

    if (response.ok) {
      return {
        status: 'success',
        message: `${data.species_name} mass = ${data.mass_g} g`
      }
    } else {
      return { status: 'error', error: data.error || 'Unknown error' }
    }
  } catch (error) {
    console.error('Network error:', error)
    return { status: 'error', error: 'Network error' }
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
  explanationModal.classList.toggle('hidden')
  inputBox.classList.add('hidden')
  goBackButton.classList.toggle('hidden')
}

// hides the explanation modal and reveals the input box
const handleGoBackClick = (event) => {
  goBackButton.classList.toggle('hidden')
  outputBox.classList.remove('moved')
  inputBox.classList.toggle('hidden')
  explanationModal.classList.toggle('hidden')
  learnMoreArrow.classList.toggle('hidden')
}

// hides the introduction modal
const handleCloseIntro = (event) => {
  introBox.classList.add('hidden')
  inputBox.classList.remove('hidden')
  beginTutorialButton.classList.remove('hidden')
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
goBackButton.addEventListener('click', handleGoBackClick)
closeIntro.addEventListener('click', handleCloseIntro)
makeVisibilityIndependent()
