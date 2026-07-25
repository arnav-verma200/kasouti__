// KASAUTI OPERATING SYSTEM FRONTEND LOGIC

// Global state cache
let currentSpot = {};
let currentCurrency = 'USD'; // 'USD' or 'INR'

// Document DOM elements
const goldRateVal = document.getElementById('goldRateVal');
const silverRateVal = document.getElementById('silverRateVal');
const currencyToggleBtn = document.getElementById('currencyToggleBtn');
const feedSettingsBtn = document.getElementById('feedSettingsBtn');
const systemResetBtn = document.getElementById('systemResetBtn');

// New global state variables
let activeTab = 'tab-standard';
let selectedTemplate = '';
let selectedMetal = 'Gold';
let selectedPurity = '22K';
let selectedGem = 'None';
let selectedSize = 'Standard';
let customImageBase64 = null;
let uploadedPhotoFilename = null;
let currentSuggestedPrice = 0;

// Radial Gauges
const gaugeSalesFill = document.getElementById('gaugeSalesFill');
const gaugeSalesText = document.getElementById('gaugeSalesText');
const badgeSales = document.getElementById('badgeSales');

const gaugeCostingFill = document.getElementById('gaugeCostingFill');
const gaugeCostingText = document.getElementById('gaugeCostingText');
const badgeCosting = document.getElementById('badgeCosting');

const gaugeProductionFill = document.getElementById('gaugeProductionFill');
const gaugeProductionText = document.getElementById('gaugeProductionText');
const badgeProduction = document.getElementById('badgeProduction');

// Queue and list containers
const auditTerminal = document.getElementById('auditTerminal');
const artisansContainer = document.getElementById('artisansContainer');
const catalogContainer = document.getElementById('catalogContainer');
const ledgerBody = document.getElementById('ledgerBody');

// Feed Settings Modal
const feedModal = document.getElementById('feedModal');
const feedModalCloseBtn = document.getElementById('feedModalCloseBtn');
const modalFeedOnline = document.getElementById('modalFeedOnline');
const modalGoldSpot = document.getElementById('modalGoldSpot');
const modalSilverSpot = document.getElementById('modalSilverSpot');
const modalUsdInr = document.getElementById('modalUsdInr');
const modalSaveSettingsBtn = document.getElementById('modalSaveSettingsBtn');

// Human Approval Drawer
const approvalDrawer = document.getElementById('approvalDrawer');
const drawerCritBadge = document.getElementById('drawerCritBadge');
const drawerOrderId = document.getElementById('drawerOrderId');
const drawerCustName = document.getElementById('drawerCustName');
const drawerMetalSpec = document.getElementById('drawerMetalSpec');
const drawerProdCheck = document.getElementById('drawerProdCheck');
const drawerReason = document.getElementById('drawerReason');
const drawerProposedVal = document.getElementById('drawerProposedVal');
const drawerTrueCostVal = document.getElementById('drawerTrueCostVal');
const drawerSuggestedVal = document.getElementById('drawerSuggestedVal');
const overrideAdjustedPrice = document.getElementById('overrideAdjustedPrice');
const overrideMemo = document.getElementById('overrideMemo');
const drawerApproveBtn = document.getElementById('drawerApproveBtn');
const drawerRejectBtn = document.getElementById('drawerRejectBtn');

// Graph visualizer SVGs
const visualizerGraph = document.getElementById('visualizerGraph');

// Seed Catalog template records (mirrored from backend)
let catalogTemplates = [];

// Initialize
window.addEventListener('DOMContentLoaded', () => {
  setupEventHandlers();
  // Fetch initial state
  fetchDashboardState().then(() => {
    populateTemplates();
    updateStdPurities();
    updateStdSizes();
    updateEstEstimates();
    drawCADBlueprint();
  });
  
  // Start polling every 5 seconds
  setInterval(fetchDashboardState, 5000);
});

// Setup event listeners
function setupEventHandlers() {
  // Currency Toggle
  currencyToggleBtn.addEventListener('click', () => {
    currentCurrency = (currentCurrency === 'USD') ? 'INR' : 'USD';
    currencyToggleBtn.textContent = currentCurrency;
    updateSpotTicker();
    refreshLedgerTable();
  });
  
  // Feed Modal controls
  feedSettingsBtn.addEventListener('click', () => {
    modalFeedOnline.checked = currentSpot.feed_online;
    modalGoldSpot.value = currentSpot.gold_usd_g;
    modalSilverSpot.value = currentSpot.silver_usd_g;
    modalUsdInr.value = currentSpot.usd_inr;
    feedModal.classList.add('active');
  });
  
  feedModalCloseBtn.addEventListener('click', () => {
    feedModal.classList.remove('active');
  });
  
  modalSaveSettingsBtn.addEventListener('click', () => {
    const payload = {
      feed_online: modalFeedOnline.checked,
      gold_usd_g: parseFloat(modalGoldSpot.value),
      silver_usd_g: parseFloat(modalSilverSpot.value),
      usd_inr: parseFloat(modalUsdInr.value)
    };
    
    fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    .then(r => r.json())
    .then(() => {
      feedModal.classList.remove('active');
      fetchDashboardState();
    });
  });
  
  // System Reset
  systemResetBtn.addEventListener('click', () => {
    if (confirm("Are you sure you want to reset all states and purge data/ledger.json?")) {
      fetch('/api/reset', { method: 'POST' })
      .then(r => r.json())
      .then(() => {
        location.reload();
      });
    }
  });

  // Tab switching
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      const tabId = btn.dataset.tab;
      document.getElementById(tabId).classList.add('active');
      activeTab = tabId;
      
      // Sync names between tabs for UX smoothness
      const stdName = document.getElementById('stdCustomerName').value;
      const custName = document.getElementById('custCustomerName').value;
      const handName = document.getElementById('handCustomerName').value;
      const activeName = stdName || custName || handName;
      document.getElementById('stdCustomerName').value = activeName;
      document.getElementById('custCustomerName').value = activeName;
      document.getElementById('handCustomerName').value = activeName;
      
      drawCADBlueprint();
    });
  });

  // Standard template cards grid events
  document.getElementById('templatesGrid').addEventListener('click', (e) => {
    const card = e.target.closest('.template-card-btn');
    if (!card) return;
    
    if (card.id === 'customOrderCardBtn') {
      const custTabBtn = document.querySelector('.tab-btn[data-tab="tab-custom"]');
      if (custTabBtn) custTabBtn.click();
      return;
    }
    
    document.querySelectorAll('.template-card-btn').forEach(c => c.classList.remove('active'));
    card.classList.add('active');
    selectedTemplate = card.dataset.template;
    
    // Load defaults dynamically
    const def = catalogTemplates.find(t => t.name === selectedTemplate);
    if (def) {
      selectedMetal = selectedTemplate.toLowerCase().includes('silver') ? 'Silver' : 'Gold';
      selectedPurity = selectedMetal === 'Gold' ? (selectedTemplate.includes('Ring') ? '18K' : '22K') : 'Sterling 92.5%';
      selectedGem = def.gemstone || 'None';
      selectedSize = def.size || 'Standard';
      document.getElementById('stdWeightG').value = def.weight_g;
      document.getElementById('stdComplexity').value = def.complexity;
      document.getElementById('stdTechnique').value = def.technique;
      
      // Update chip visual states
      updateChipVisuals('stdMetalChips', selectedMetal);
      updateStdPurities();
      updateChipVisuals('stdPurityChips', selectedPurity);
      updateChipVisuals('stdGemChips', selectedGem);
      updateStdSizes();
      updateChipVisuals('stdSizeChips', selectedSize);
      
      drawCADBlueprint();
    }
  });

  // Metal chips standard order
  document.getElementById('stdMetalChips').addEventListener('click', (e) => {
    const btn = e.target.closest('.chip-btn');
    if (!btn) return;
    selectedMetal = btn.dataset.val;
    updateChipVisuals('stdMetalChips', selectedMetal);
    updateStdPurities();
    drawCADBlueprint();
  });

  // Purity chips standard order
  document.getElementById('stdPurityChips').addEventListener('click', (e) => {
    const btn = e.target.closest('.chip-btn');
    if (!btn) return;
    selectedPurity = btn.dataset.val;
    updateChipVisuals('stdPurityChips', selectedPurity);
    drawCADBlueprint();
  });

  // Gemstone chips standard order
  document.getElementById('stdGemChips').addEventListener('click', (e) => {
    const btn = e.target.closest('.chip-btn');
    if (!btn) return;
    selectedGem = btn.dataset.val;
    updateChipVisuals('stdGemChips', selectedGem);
  });

  // Size chips standard order
  document.getElementById('stdSizeChips').addEventListener('click', (e) => {
    const btn = e.target.closest('.chip-btn');
    if (!btn) return;
    selectedSize = btn.dataset.val;
    updateChipVisuals('stdSizeChips', selectedSize);
  });

  // Weight increment / decrement buttons standard order
  document.getElementById('weightMinusBtn').addEventListener('click', () => {
    const input = document.getElementById('stdWeightG');
    let val = parseFloat(input.value) || 0;
    if (val > 0.2) {
      input.value = (val - 0.5).toFixed(1);
      drawCADBlueprint();
    }
  });
  
  document.getElementById('weightPlusBtn').addEventListener('click', () => {
    const input = document.getElementById('stdWeightG');
    let val = parseFloat(input.value) || 0;
    input.value = (val + 0.5).toFixed(1);
    drawCADBlueprint();
  });

  document.getElementById('stdWeightG').addEventListener('input', drawCADBlueprint);

  // Custom tab change estimators
  document.getElementById('custMetalType').addEventListener('change', () => {
    updateCustPurityOptions();
    updateEstEstimates();
    drawCADBlueprint();
  });
  document.getElementById('custKaratPurity').addEventListener('change', () => {
    updateEstEstimates();
    drawCADBlueprint();
  });
  document.getElementById('custWeightG').addEventListener('input', () => {
    updateEstEstimates();
    drawCADBlueprint();
  });
  document.getElementById('custComplexity').addEventListener('change', () => {
    updateEstEstimates();
    drawCADBlueprint();
  });
  document.getElementById('custTechnique').addEventListener('change', () => {
    drawCADBlueprint();
  });

  // Dropzone file select / dragover
  const dropzone = document.getElementById('refDropzone');
  const fileInput = document.getElementById('refFileInput');
  const removeImgBtn = document.getElementById('refRemoveImgBtn');
  
  dropzone.addEventListener('click', (e) => {
    if (e.target.closest('.remove-img-btn')) return;
    fileInput.click();
  });
  
  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });
  
  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });
  
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleRefImageUpload(e.dataTransfer.files[0]);
    }
  });
  
  fileInput.addEventListener('change', (e) => {
    if (fileInput.files && fileInput.files[0]) {
      handleRefImageUpload(fileInput.files[0]);
    }
  });

  removeImgBtn.addEventListener('click', () => {
    customImageBase64 = null;
    document.getElementById('refPreviewContainer').style.display = 'none';
    document.getElementById('dropzoneText').style.display = 'block';
    fileInput.value = '';
  });


  // Forms submit
  document.getElementById('stdIntakeForm').addEventListener('submit', handleStdSubmit);
  document.getElementById('customIntakeForm').addEventListener('submit', handleCustSubmit);
  document.getElementById('handoffIntakeForm').addEventListener('submit', handleHandoffSubmit);

  // Override justification reason chips multi-select toggle
  document.getElementById('overrideReasonChips').addEventListener('click', (e) => {
    const btn = e.target.closest('.chip-btn');
    if (!btn) return;
    btn.classList.toggle('active');
  });

  // Call Karigar escalation events
  const customCallKarigarBtn = document.getElementById('customCallKarigarBtn');
  if (customCallKarigarBtn) {
    customCallKarigarBtn.addEventListener('click', handleCustomCallKarigar);
  }
  const submitKarigarOutcomeBtn = document.getElementById('submitKarigarOutcomeBtn');
  if (submitKarigarOutcomeBtn) {
    submitKarigarOutcomeBtn.addEventListener('click', handleSubmitKarigarOutcome);
  }

  // Override actions
  drawerApproveBtn.addEventListener('click', () => handleOverrideDecision('approve'));
  drawerRejectBtn.addEventListener('click', () => handleOverrideDecision('reject'));

  // Receipt Modal actions
  document.getElementById('receiptCloseBtn').addEventListener('click', () => {
    document.getElementById('receiptOverlay').classList.remove('active');
  });
  document.getElementById('receiptConfirmBtn').addEventListener('click', () => {
    document.getElementById('receiptOverlay').classList.remove('active');
  });
  document.getElementById('receiptPrintBtn').addEventListener('click', () => {
    window.print();
  });
}

// Fetch dashboard state
let lastLogCount = 0;
let isPolling = false;

async function fetchDashboardState() {
  if (isPolling) return; // Prevent overlapping queries
  try {
    isPolling = true;
    const response = await fetch('/api/dashboard');
    const data = await response.json();
    
    // Save to globals
    currentSpot = data.spot;
    catalogTemplates = data.catalog;
    
    // Update UI components
    updateSpotTicker();
    updateTrustGauges(data.trust);
    updateArtisansList(data.artisans);
    updateLedgerTable(data.ledger);
    updateTerminalLogs(data.audit_log);
    
    // Check pending approval
    toggleApprovalDrawer(data.pending);
  } catch (error) {
    console.error("Dashboard Poll failed:", error);
  } finally {
    isPolling = false;
  }
}

// Update Spot rate ticker
function updateSpotTicker() {
  if (!currentSpot.gold_usd_g) return;
  const isUSD = currentCurrency === 'USD';
  const mult = isUSD ? 1.0 : currentSpot.usd_inr;
  const symb = isUSD ? '$' : '₹';
  
  const goldPrice = currentSpot.gold_usd_g * mult;
  const silverPrice = currentSpot.silver_usd_g * mult;
  
  goldRateVal.textContent = `${symb}${goldPrice.toFixed(2)}`;
  silverRateVal.textContent = `${symb}${silverPrice.toFixed(2)}`;
  
  // Highlight feed state
  const ticker = document.getElementById('rateTicker');
  if (currentSpot.feed_online) {
    ticker.style.borderColor = 'var(--border-light)';
    ticker.title = "Live spot rates active (jitter loop running)";
  } else {
    ticker.style.borderColor = 'rgba(231, 76, 60, 0.4)';
    ticker.title = "Spot rate feed OFFLINE (Calculations locked)";
  }
}

// Update Trust score gauges
function updateTrustGauges(trust) {
  Object.keys(trust).forEach(agent => {
    const score = trust[agent];
    const percentage = score * 100;
    
    // Find matching DOM nodes
    const fillNode = document.getElementById(`gauge${capitalize(agent)}Fill`);
    const textNode = document.getElementById(`gauge${capitalize(agent)}Text`);
    const badgeNode = document.getElementById(`badge${capitalize(agent)}`);
    
    if (fillNode && textNode && badgeNode) {
      // Stroke dash offset calculation (R=42, circumference ~ 264)
      const offset = 264 * (1 - score);
      fillNode.style.strokeDashoffset = offset;
      
      // Update Text
      textNode.textContent = score.toFixed(2);
      
      // Update badge and fill colors
      if (score >= 0.85) {
        badgeNode.textContent = "AUTONOMOUS";
        badgeNode.className = "badge autonomous";
        fillNode.style.stroke = "var(--color-green)";
      } else {
        badgeNode.textContent = "VERIFY LOCK";
        badgeNode.className = "badge verify-lock";
        fillNode.style.stroke = "var(--color-red)";
      }
    }
  });
}

// Update Artisan queue list
function updateArtisansList(artisans) {
  artisansContainer.innerHTML = '';
  artisans.forEach(a => {
    const isBusy = a.backlog_days >= 8;
    const card = document.createElement('div');
    card.className = 'artisan-card';
    card.innerHTML = `
      <div class="art-info">
        <span class="art-name">${a.name}</span>
        <span class="art-spec">${a.specialty}</span>
      </div>
      <div class="art-status">
        <span class="art-backlog">${a.backlog_days}d Backlog</span>
        <span class="badge-status ${isBusy ? 'busy' : 'idle'}">${isBusy ? 'Busy' : 'Idle'}</span>
      </div>
    `;
    artisansContainer.appendChild(card);
  });
}

let templatePopulated = false;

function populateTemplates() {
  if (templatePopulated) return;
  
  const catalogList = document.getElementById('catalogContainer');
  catalogList.innerHTML = '';
  
  const grid = document.getElementById('templatesGrid');
  grid.innerHTML = '';
  
  catalogTemplates.forEach((t, idx) => {
    // Add item to list card
    const card = document.createElement('div');
    card.className = 'catalog-item';
    card.innerHTML = `
      <div class="catalog-header">
        <span class="cat-name">${t.name}</span>
        <span class="cat-tag">${t.complexity.toUpperCase()}</span>
      </div>
      <div class="cat-specs">
        Weight: ${t.weight_g}g | Technique: ${t.technique}
      </div>
    `;
    
    card.addEventListener('click', () => {
      // Trigger click on corresponding Standard card
      const stdCard = document.querySelector(`.template-card-btn[data-template="${t.name}"]`);
      if (stdCard) {
        // If we are not on standard tab, switch to standard tab first
        const stdTabBtn = document.querySelector('.tab-btn[data-tab="tab-standard"]');
        if (stdTabBtn) stdTabBtn.click();
        stdCard.click();
      }
    });
    
    catalogList.appendChild(card);

    // Populate templatesGrid
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `template-card-btn ${idx === 0 ? 'active' : ''}`;
    btn.dataset.template = t.name;
    
    let shortName = t.name.split(' ').slice(1).join(' ');
    if (!shortName) shortName = t.name;
    
    btn.innerHTML = `
      <span class="template-card-name">${shortName}</span>
      <span class="template-card-desc">${t.weight_g}g · ${t.finish} · ${capitalize(t.technique)}</span>
    `;
    grid.appendChild(btn);
  });

  // Append Custom Order Card trigger
  const customBtn = document.createElement('button');
  customBtn.type = 'button';
  customBtn.className = 'template-card-btn custom-trigger-btn';
  customBtn.id = 'customOrderCardBtn';
  customBtn.innerHTML = `
    <span class="template-card-name" style="color: var(--accent-gold);">Custom Order</span>
    <span class="template-card-desc">Bespoke specs & uploads</span>
  `;
  grid.appendChild(customBtn);
  
  if (catalogTemplates.length > 0) {
    selectedTemplate = catalogTemplates[0].name;
    const def = catalogTemplates[0];
    selectedMetal = selectedTemplate.toLowerCase().includes('silver') ? 'Silver' : 'Gold';
    selectedPurity = selectedMetal === 'Gold' ? (selectedTemplate.includes('Ring') ? '18K' : '22K') : 'Sterling 92.5%';
    selectedGem = def.gemstone || 'None';
    selectedSize = def.size || 'Standard';
    document.getElementById('stdWeightG').value = def.weight_g;
    document.getElementById('stdComplexity').value = def.complexity;
    document.getElementById('stdTechnique').value = def.technique;
  }
  
  templatePopulated = true;
  updateCustPurityOptions();
}

// Update active states on visual chip groups
function updateChipVisuals(groupId, activeVal) {
  const group = document.getElementById(groupId);
  if (!group) return;
  group.querySelectorAll('.chip-btn').forEach(btn => {
    if (btn.dataset.val === activeVal) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

// Generate purity chips based on metal choice in standard tab
function updateStdPurities() {
  const container = document.getElementById('stdPurityChips');
  if (!container) return;
  container.innerHTML = '';
  
  let purities = [];
  if (selectedMetal === 'Gold') {
    purities = ['24K', '22K', '18K', '14K'];
    if (!purities.includes(selectedPurity)) selectedPurity = '22K';
  } else {
    purities = ['Sterling 92.5%', 'Pure Silver'];
    if (!purities.includes(selectedPurity)) selectedPurity = 'Sterling 92.5%';
  }
  
  purities.forEach(p => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `chip-btn ${p === selectedPurity ? 'active' : ''}`;
    btn.dataset.val = p;
    btn.textContent = p;
    container.appendChild(btn);
  });
}

function getSizesForTemplate(templateName) {
  if (templateName.includes('Ring')) return ["5", "6", "7", "8", "9", "10"];
  if (templateName.includes('Set')) return ["Collar 400mm", "Collar 420mm", "Collar 450mm"];
  if (templateName.includes('Kada')) return ["Diam 58mm", "Diam 62mm", "Diam 66mm"];
  return ["Standard"];
}

// Generate sizes chips dynamically based on template design
function updateStdSizes() {
  const container = document.getElementById('stdSizeChips');
  if (!container) return;
  container.innerHTML = '';
  
  const sizes = getSizesForTemplate(selectedTemplate);
  if (!sizes.includes(selectedSize)) selectedSize = sizes[0];
  
  sizes.forEach(s => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `chip-btn ${s === selectedSize ? 'active' : ''}`;
    btn.dataset.val = s;
    btn.textContent = s;
    container.appendChild(btn);
  });
}

// Custom Tab: Swap purity options
function updateCustPurityOptions() {
  const metal = document.getElementById('custMetalType').value;
  const select = document.getElementById('custKaratPurity');
  if (!select) return;
  select.innerHTML = '';
  
  if (metal === 'Gold') {
    const karats = ['24K', '22K', '18K', '14K'];
    karats.forEach(k => {
      const opt = document.createElement('option');
      opt.value = k;
      opt.textContent = k;
      if (k === '22K') opt.selected = true;
      select.appendChild(opt);
    });
  } else {
    const purities = ['Sterling 92.5%', 'Pure Silver'];
    purities.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p;
      opt.textContent = p;
      select.appendChild(opt);
    });
  }
}

// Custom Tab: Dynamic Retail Estimator
function updateEstEstimates() {
  const metal = document.getElementById('custMetalType').value;
  const purity = document.getElementById('custKaratPurity').value;
  const weight = parseFloat(document.getElementById('custWeightG').value) || 0;
  const comp = document.getElementById('custComplexity').value;
  
  if (!currentSpot.gold_usd_g) return;
  
  const spot = metal === 'Gold' ? currentSpot.gold_usd_g : currentSpot.silver_usd_g;
  let purityRatio = 1.0;
  if (metal === 'Gold') {
    const karat = parseFloat(purity.replace(/[^0-9.]/g, '')) || 22;
    purityRatio = karat / 24;
  } else {
    if (purity.includes('92.5')) purityRatio = 0.925;
  }
  const metalRate = spot * purityRatio;
  
  let makingCharge = 8.0;
  if (comp === 'low') makingCharge = 5.0;
  if (comp === 'high') makingCharge = 12.0;
  
  const trueCost = (metalRate * weight) + (makingCharge * weight) + 45.00;
  const estRetail = trueCost * 1.22;
  
  let baseDays = 5;
  if (comp === 'low') baseDays = 2;
  if (comp === 'high') baseDays = 9;
  
  document.getElementById('estTrueCost').textContent = `$${trueCost.toFixed(2)}`;
  document.getElementById('estTimeline').textContent = `${baseDays + 2} days`;
  document.getElementById('estRetail').textContent = `$${estRetail.toFixed(2)}`;
}

// Animate Node Graph Visualizer sequential flow
function runGraphAnimation(outcome, callback) {
  // Clear classes
  const nodes = ['intake', 'sales', 'costing', 'production', 'override', 'orchestrator'];
  const edges = ['intake-sales', 'sales-costing', 'costing-production', 'costing-override', 'production-orchestrator', 'override-orchestrator', 'orchestrator-ledger'];
  
  nodes.forEach(n => {
    const node = document.getElementById(`node-${n}`);
    if (node) node.className = 'graph-node idle';
  });
  edges.forEach(e => {
    const edge = document.getElementById(`edge-${e}`);
    if (edge) edge.className = 'graph-edge';
  });
  
  // Define sequence flow timeline
  let step = 0;
  
  // Transition function
  function nextStep() {
    step++;
    if (step === 1) {
      // Highlight Intake Node
      setNodeState('intake', 'processing');
      setTimeout(nextStep, 600);
    } else if (step === 2) {
      setNodeState('intake', 'success');
      setEdgeState('intake-sales', 'active');
      setNodeState('sales', 'processing');
      setTimeout(nextStep, 700);
    } else if (step === 3) {
      setNodeState('sales', 'success');
      setEdgeState('sales-costing', 'active');
      setNodeState('costing', 'processing');
      setTimeout(nextStep, 700);
    } else if (step === 4) {
      // Costing branch check
      if (outcome.status === 'pending' && outcome.reason === 'feed_offline') {
        // Feed offline -> Straight to human override
        setNodeState('costing', 'blocked');
        setEdgeState('costing-override', 'active');
        setNodeState('override', 'processing');
        setTimeout(() => {
          setNodeState('override', 'blocked');
          setEdgeState('override-orchestrator', 'active');
          setNodeState('orchestrator', 'blocked');
          if (callback) callback();
        }, 800);
      } else {
        setNodeState('costing', 'success');
        
        // Margin/Trust evaluations
        if (outcome.status === 'auto_executed') {
          // Normal success execution path
          setEdgeState('costing-production', 'active');
          setNodeState('production', 'processing');
          setTimeout(() => {
            setNodeState('production', 'success');
            setEdgeState('production-orchestrator', 'active');
            setNodeState('orchestrator', 'processing');
            setTimeout(() => {
              setNodeState('orchestrator', 'success');
              setEdgeState('orchestrator-ledger', 'active');
              if (callback) callback();
            }, 600);
          }, 800);
        } else {
          // Low trust / deficit -> goes to override drawer
          setEdgeState('costing-override', 'active');
          setNodeState('override', 'processing');
          // Wait on operator response, so we stop pulsing at override node
          setTimeout(() => {
            setNodeState('override', 'blocked');
            if (callback) callback();
          }, 800);
        }
      }
    }
  }
  
  nextStep();
}

function setNodeState(id, state) {
  const node = document.getElementById(`node-${id}`);
  if (node) node.className = `graph-node ${state}`;
}

function setEdgeState(id, state) {
  const edge = document.getElementById(`edge-${id}`);
  if (edge) {
    if (state === 'active') {
      edge.classList.add('active');
      edge.style.markerEnd = 'url(#arrow-active)';
    } else {
      edge.classList.remove('active');
      edge.style.markerEnd = 'url(#arrow)';
    }
  }
}

// File Upload Drag and Drop Reader
function handleRefImageUpload(file) {
  const reader = new FileReader();
  reader.onload = (event) => {
    customImageBase64 = event.target.result;
    document.getElementById('refPreviewImg').src = customImageBase64;
    document.getElementById('refPreviewContainer').style.display = 'flex';
    document.getElementById('dropzoneText').style.display = 'none';
  };
  reader.readAsDataURL(file);

  const formData = new FormData();
  formData.append('file', file);
  
  fetch('/api/upload', {
    method: 'POST',
    body: formData
  })
  .then(r => r.json())
  .then(data => {
    if (data.status === 'success') {
      uploadedPhotoFilename = data.filename;
      console.log('Uploaded image file to server:', uploadedPhotoFilename);
    }
  })
  .catch(err => {
    console.error('File upload failed:', err);
  });
}


// Standard Intake form handler
function handleStdSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById('stdSubmitBtn');
  btn.disabled = true;
  btn.style.opacity = '0.5';
  
  const payload = {
    customer_name: document.getElementById('stdCustomerName').value.trim(),
    metal: selectedMetal,
    karat_or_purity: selectedPurity,
    weight_g: parseFloat(document.getElementById('stdWeightG').value) || 0.1,
    budget: document.getElementById('stdCustomerBudget').value ? parseFloat(document.getElementById('stdCustomerBudget').value) : null,
    deadline_days: parseInt(document.getElementById('stdDeadlineDays').value) || 14,
    complexity: document.getElementById('stdComplexity').value,
    technique: document.getElementById('stdTechnique').value,
    gemstone: selectedGem,
    size: selectedSize
  };
  
  fetch('/api/intake', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(res => {
    runGraphAnimation(res, () => {
      btn.disabled = false;
      btn.style.opacity = '1';
      fetchDashboardState().then(() => {
        if (res.status === 'auto_executed') {
          showOrderReceipt(res.order_id);
        }
      });
    });
  })
  .catch(err => {
    console.error("Standard intake failed:", err);
    btn.disabled = false;
    btn.style.opacity = '1';
    alert("Intake evaluation failed. Spot rate feed might be offline or invalid parameters.");
  });
}

// Custom Bespoke Intake form handler
function handleCustSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById('custSubmitBtn');
  btn.disabled = true;
  btn.style.opacity = '0.5';
  
  const payload = {
    customer_name: document.getElementById('custCustomerName').value.trim(),
    metal: document.getElementById('custMetalType').value,
    karat_or_purity: document.getElementById('custKaratPurity').value,
    weight_g: parseFloat(document.getElementById('custWeightG').value) || 1.0,
    budget: document.getElementById('custCustomerBudget').value ? parseFloat(document.getElementById('custCustomerBudget').value) : null,
    deadline_days: parseInt(document.getElementById('custDeadlineDays').value) || 21,
    complexity: document.getElementById('custComplexity').value,
    technique: document.getElementById('custTechnique').value,
    gemstone: "None",
    size: "Bespoke",
    photo_filename: uploadedPhotoFilename || null,
    workshop_notes: document.getElementById('custNotes').value.trim() || null,
    is_custom: true
  };
  
  if (document.getElementById('custNotes').value.trim()) {
    payload.size = `Bespoke | Note: ${document.getElementById('custNotes').value.trim()}`;
  }
  
  fetch('/api/intake', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(res => {
    runGraphAnimation(res, () => {
      btn.disabled = false;
      btn.style.opacity = '1';
      
      // Clear custom preview images
      uploadedPhotoFilename = null;
      customImageBase64 = null;
      document.getElementById('refPreviewContainer').style.display = 'none';
      document.getElementById('dropzoneText').style.display = 'block';
      document.getElementById('refFileInput').value = '';
      
      document.getElementById('customIntakeForm').reset();
      
      fetchDashboardState().then(() => {
        if (res.status === 'auto_executed') {
          showOrderReceipt(res.order_id);
        }
      });
    });
  })
  .catch(err => {
    console.error("Custom intake failed:", err);
    btn.disabled = false;
    btn.style.opacity = '1';
    alert("Custom bespoke intake failed.");
  });
}

function handleCustomCallKarigar() {
  const customerName = document.getElementById('custCustomerName').value.trim();
  const designNotes = document.getElementById('custNotes').value.trim();
  
  if (!customerName) {
    alert("Please enter the customer name before escalating.");
    return;
  }
  if (!designNotes) {
    alert("Please enter the design crafting notes before escalating.");
    return;
  }
  
  const callBtn = document.getElementById('customCallKarigarBtn');
  callBtn.disabled = true;
  callBtn.style.opacity = '0.5';
  
  const payload = {
    customer_name: customerName,
    notes: designNotes
  };
  
  fetch('/api/handoff', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(res => {
    setNodeState('intake', 'success');
    setEdgeState('intake-sales', 'active');
    setNodeState('sales', 'blocked');
    
    document.getElementById('karigarHandoffId').value = res.handoff_id;
    document.getElementById('karigarOutcomeSection').style.display = 'block';
    callBtn.style.display = 'none';
    
    fetchDashboardState();
    alert(`Escalated to Shankar Das. Handoff ID: ${res.handoff_id}. Please log the final resolution below.`);
  })
  .catch(err => {
    console.error("Karigar handoff escalation failed:", err);
    callBtn.disabled = false;
    callBtn.style.opacity = '1';
    alert("Escalation failed.");
  });
}

function handleSubmitKarigarOutcome() {
  const handoffId = document.getElementById('karigarHandoffId').value;
  const customerName = document.getElementById('custCustomerName').value.trim();
  const agreedPrice = parseFloat(document.getElementById('karigarAgreedPrice').value) || 0;
  const notes = document.getElementById('karigarOutcomeNotes').value.trim();
  
  if (agreedPrice <= 0) {
    alert("Please enter a valid agreed price.");
    return;
  }
  if (!notes) {
    alert("Please enter outcome resolution notes.");
    return;
  }
  
  const submitBtn = document.getElementById('submitKarigarOutcomeBtn');
  submitBtn.disabled = true;
  submitBtn.style.opacity = '0.5';
  
  const payload = {
    handoff_id: handoffId,
    customer_name: customerName,
    agreed_price: agreedPrice,
    notes: notes
  };
  
  fetch('/api/handoff-outcome', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(res => {
    setNodeState('orchestrator', 'success');
    setEdgeState('orchestrator-ledger', 'active');
    
    setTimeout(() => {
      document.getElementById('customIntakeForm').reset();
      document.getElementById('karigarOutcomeSection').style.display = 'none';
      
      const callBtn = document.getElementById('customCallKarigarBtn');
      callBtn.style.display = 'block';
      callBtn.disabled = false;
      callBtn.style.opacity = '1';
      
      uploadedPhotoFilename = null;
      customImageBase64 = null;
      document.getElementById('refPreviewContainer').style.display = 'none';
      document.getElementById('dropzoneText').style.display = 'block';
      
      submitBtn.disabled = false;
      submitBtn.style.opacity = '1';
      
      fetchDashboardState();
      alert("Resolution successfully logged in ledger!");
    }, 1000);
  })
  .catch(err => {
    console.error("Resolution outcome submission failed:", err);
    submitBtn.disabled = false;
    submitBtn.style.opacity = '1';
    alert("Outcome submission failed.");
  });
}

function updatePriceComparisonStatus(suggestedPrice) {
  const adjInput = document.getElementById('overrideAdjustedPrice');
  const adjCard = document.getElementById('anchorAdjustedCard');
  const adjustedVal = parseFloat(adjInput.value) || 0;
  
  adjCard.classList.remove('shortfall-red', 'cleared-green');
  
  if (adjustedVal < suggestedPrice) {
    adjCard.classList.add('shortfall-red');
  } else {
    adjCard.classList.add('cleared-green');
  }
}

// Handoff form submit handler (Bypass exception channel)
function handleHandoffSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById('handSubmitBtn');
  btn.disabled = true;
  btn.style.opacity = '0.5';
  
  const payload = {
    customer_name: document.getElementById('handCustomerName').value.trim(),
    notes: document.getElementById('handNotes').value.trim()
  };
  
  fetch('/api/handoff', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(res => {
    // Log exception animation state visually (we simulate exception bypass on graph)
    setNodeState('intake', 'success');
    setEdgeState('intake-sales', 'active');
    setNodeState('sales', 'blocked'); // Bypassed standard sales logic
    
    setTimeout(() => {
      setNodeState('orchestrator', 'success');
      setEdgeState('orchestrator-ledger', 'active');
      
      btn.disabled = false;
      btn.style.opacity = '1';
      
      fetchDashboardState().then(() => {
        showHandoffReceipt(res);
      });
    }, 1000);
  })
  .catch(err => {
    console.error("Handoff post failed:", err);
    btn.disabled = false;
    btn.style.opacity = '1';
    alert("Failed to submit handoff exception.");
  });
}

function showOrderReceipt(orderId) {
  fetch(`/api/invoice/${orderId}`)
  .then(r => {
    if (!r.ok) throw new Error("Failed to load invoice details");
    return r.json();
  })
  .then(order => {
    document.getElementById('rcptOrderType').textContent = order.resolution_pathway.toUpperCase();
    document.getElementById('rcptOrderId').textContent = order.order_id;
    document.getElementById('rcptCustomerName').textContent = order.customer_name;
    document.getElementById('rcptSpecs').textContent = order.details;
    
    // Parse gemstone and size
    const gemMatch = order.details.match(/Gem:\s*([A-Za-z]+)/);
    const sizeMatch = order.details.match(/Size:\s*([^|]+)/);
    const gemVal = gemMatch ? gemMatch[1] : "None";
    const sizeVal = sizeMatch ? sizeMatch[1].trim() : "Standard";
    
    // Render cost breakdown
    const breakdown = renderCostBreakdown(order);
    
    if (breakdown.hasGem) {
      document.getElementById('rcptGemRow').style.display = 'flex';
      document.getElementById('rcptGemVal').textContent = `${breakdown.gemVal}`;
    } else {
      document.getElementById('rcptGemRow').style.display = 'none';
    }
    
    document.getElementById('rcptSpotRate').textContent = breakdown.liveMetalRateConverted;
    document.getElementById('rcptPathway').textContent = order.resolution_pathway;
    document.getElementById('rcptTotalUsd').textContent = breakdown.finalPriceUSD;
    document.getElementById('rcptTotalInr').textContent = breakdown.finalPriceConverted;
    
    // Workshop slip Details
    document.getElementById('rcptDeadline').textContent = "Allocated";
    document.getElementById('rcptSize').textContent = sizeVal;
    
    // Render sketch preview if custom
    const sketchRow = document.getElementById('rcptSketchRow');
    if (activeTab === 'tab-custom' && customImageBase64) {
      document.getElementById('rcptSketchImg').src = customImageBase64;
      sketchRow.style.display = 'block';
    } else {
      sketchRow.style.display = 'none';
    }
    
    document.getElementById('rcptArtisan').textContent = "Allocated Master Artisan";
    
    // Invoice details
    const invoice = order.invoice || {
      invoice_id: `INV-${order.order_id}`,
      payment_status: "unpaid",
      amount_paid: 0.0,
      tax_amount: 0.0,
      paid_at: null
    };
    
    const statusEl = document.getElementById('rcptPaymentStatus');
    const paidEl = document.getElementById('rcptAmountPaid');
    const paySection = document.getElementById('rcptRecordPaymentSection');
    const payInput = document.getElementById('rcptPaymentInput');
    const payBtn = document.getElementById('rcptRecordPaymentBtn');
    
    statusEl.textContent = invoice.payment_status.toUpperCase();
    statusEl.className = `pathway-badge ${invoice.payment_status === 'paid' ? 'approved' : (invoice.payment_status === 'partial' ? 'auto' : 'rejected')}`;
    
    paidEl.textContent = `$${invoice.amount_paid.toFixed(2)}`;
    
    if (invoice.payment_status !== 'paid') {
      paySection.style.display = 'block';
      payInput.value = '';
      const remaining = order.final_price - invoice.amount_paid;
      payInput.max = remaining.toFixed(2);
      payInput.placeholder = `Max $${remaining.toFixed(2)}`;
      
      payBtn.onclick = () => {
        const amount = parseFloat(payInput.value);
        if (isNaN(amount) || amount <= 0) {
          alert("Please enter a valid payment amount.");
          return;
        }
        if (amount > remaining) {
          alert(`Payment exceeds remaining balance. Max allowed: $${remaining.toFixed(2)}`);
          return;
        }
        
        payBtn.disabled = true;
        payBtn.textContent = '...';
        
        fetch('/api/payment', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            order_id: order.order_id,
            amount: amount
          })
        })
        .then(res => {
          if (!res.ok) {
            return res.json().then(err => { throw new Error(err.detail || "Payment failed"); });
          }
          return res.json();
        })
        .then(() => {
          // Re-render receipt
          showOrderReceipt(order.order_id);
          fetchDashboardState();
        })
        .catch(err => {
          alert(err.message);
        })
        .finally(() => {
          payBtn.disabled = false;
          payBtn.textContent = 'Pay';
        });
      };
    } else {
      paySection.style.display = 'none';
    }
    
    // Show Receipt modal overlay
    document.getElementById('receiptOverlay').classList.add('active');
  })
  .catch(err => {
    console.error("Receipt error:", err);
    alert("Failed to load invoice details: " + err.message);
  });
}

function showHandoffReceipt(res) {
  document.getElementById('rcptOrderType').textContent = "KARIGAR HANDOFF PASS";
  document.getElementById('rcptOrderId').textContent = res.handoff_id;
  document.getElementById('rcptCustomerName').textContent = res.customer_name;
  document.getElementById('rcptSpecs').textContent = "Physical inspection & bespoke molds bypass standard OS forms";
  document.getElementById('rcptGemRow').style.display = 'none';
  
  document.getElementById('rcptSpotRate').textContent = "TBD by Shankar Das";
  document.getElementById('rcptPathway').textContent = "Bypassed OS Gate";
  document.getElementById('rcptTotalUsd').textContent = "TBD";
  document.getElementById('rcptTotalInr').textContent = "TBD";
  
  // Workshop SOP slip
  document.getElementById('rcptArtisan').textContent = "शंकर दास Shankar Das (Head Karigar)";
  document.getElementById('rcptDeadline').textContent = "Immediate Handoff";
  document.getElementById('rcptSize').textContent = "Bespoke Shape Mold Rebuild";
  document.getElementById('rcptSketchRow').style.display = 'none';
  
  // Hide invoice/payment fields in handoff receipt
  document.getElementById('rcptRecordPaymentSection').style.display = 'none';
  document.getElementById('rcptPaymentStatus').textContent = "TBD";
  document.getElementById('rcptPaymentStatus').className = "pathway-badge auto";
  document.getElementById('rcptAmountPaid').textContent = "$0.00";
  
  document.getElementById('receiptOverlay').classList.add('active');
}

// Update Audit Terminal
function updateTerminalLogs(audit_log) {
  // Only redraw if length changed to keep terminal scrolling state stable
  if (audit_log.length === lastLogCount) return;
  
  auditTerminal.innerHTML = '';
  audit_log.forEach((log, idx) => {
    const line = document.createElement('div');
    line.className = 'terminal-line';
    
    // Pick log text formatting
    let logTypeClass = 'log-txt-info';
    if (log.text.includes('SYSTEM_EXCEPTION') || log.text.includes('CRITICAL') || log.text.includes('Error')) {
      logTypeClass = 'log-txt-error';
    } else if (log.text.includes('Auto-executing') || log.text.includes('success') || log.text.includes('APPROVED')) {
      logTypeClass = 'log-txt-success';
    } else if (log.text.includes('Negotiation Cap Hit') || log.text.includes('cap_hit') || log.text.includes('CAP HIT')) {
      logTypeClass = 'log-txt-cap-hit';
    } else if (log.text.includes('fallback') || log.text.includes('FALLBACK') || log.text.includes('falling back')) {
      logTypeClass = 'log-txt-fallback';
    } else if (log.text.includes('Routing') || log.text.includes('deficit') || log.text.includes('Safety verification lock')) {
      logTypeClass = 'log-txt-warning';
    }
    
    const statusTag = log.status ? `<span class="log-status font-mono" style="color: var(--accent-gold); font-size: 0.7rem; border: 1px solid var(--border-light); padding: 0.05rem 0.25rem; border-radius: 3px; margin-right: 0.4rem; background-color: rgba(197, 168, 128, 0.05);">${log.status}</span>` : '';
    line.innerHTML = `<span class="log-ts">[${log.ts.split(' ')[1]}]</span> ${statusTag}<span class="${logTypeClass}">${escapeHTML(log.text)}</span>`;
    auditTerminal.appendChild(line);
    
    // Inject the Markdown Recalc summary table inside the terminal log if it's the last action resolving the order
    // We look for keyword APPROVED, Auto-executing, or REJECTED
    if (idx === audit_log.length - 1 && (log.text.includes('Auto-executing') || log.text.includes('APPROVED') || log.text.includes('REJECTED'))) {
      injectSummaryTable();
    }
  });
  
  lastLogCount = audit_log.length;
  // Scroll to bottom
  auditTerminal.scrollTop = auditTerminal.scrollHeight;
}

// Inject ASCII/Markdown table summarizing latest transaction cost & margin
function injectSummaryTable() {
  const container = document.createElement('pre');
  container.className = 'terminal-line log-txt-info';
  
  let m, k, w, c;
  if (activeTab === 'tab-standard') {
    m = selectedMetal;
    k = selectedPurity;
    w = document.getElementById('stdWeightG').value;
    c = document.getElementById('stdComplexity').value;
  } else {
    m = document.getElementById('custMetalType').value;
    k = document.getElementById('custKaratPurity').value;
    w = document.getElementById('custWeightG').value;
    c = document.getElementById('custComplexity').value;
  }
  
  // Generate a mock formatted box
  const tableStr = `
+-------------------------------------------------+
|          LIVE ATELIER CALCULATION SUMMARY       |
+-------------------------------------------------+
|  Metal Type      | ${m} (${k})
|  Target weight   | ${w} g
|  Artisan Queue   | Allocated based on specialization
|  Complexity      | Charge tier: ${c}
|  Notion Sync     | DEFERRED (Sync hook stubbed)
+-------------------------------------------------+
|  Cycle complete  | Committing resolved state...   |
+-------------------------------------------------+`;
  container.textContent = tableStr;
  auditTerminal.appendChild(container);
}

// Toggle slide-in drawer for Operator approvals
let currentPendingId = null;
let selectedOverrideReason = null;

function toggleApprovalDrawer(pending) {
  if (pending) {
    if (currentPendingId === pending.id) return;
    currentPendingId = pending.id;
    
    // Open drawer
    approvalDrawer.classList.add('active');
    
    // Populate data
    drawerOrderId.textContent = pending.id;
    drawerCustName.textContent = pending.customer_name;
    drawerMetalSpec.textContent = `${pending.weight_g}g of ${pending.karat_or_purity} ${pending.metal} (${pending.complexity})`;
    drawerReason.textContent = pending.override_reason || "Verify safety lock.";
    
    // Highlight Critical vs Safety
    if (pending.critical_override) {
      drawerCritBadge.style.display = 'inline-block';
      drawerCritBadge.textContent = 'CRITICAL OVERRIDE';
      drawerCritBadge.style.backgroundColor = 'rgba(231, 76, 60, 0.15)';
      drawerCritBadge.style.color = 'var(--color-red)';
    } else {
      drawerCritBadge.style.display = 'inline-block';
      drawerCritBadge.textContent = 'SAFETY LOCK';
      drawerCritBadge.style.backgroundColor = 'rgba(243, 156, 18, 0.15)';
      drawerCritBadge.style.color = 'var(--color-amber)';
    }
    
    // Parse feasibility note to extract values for badges row
    const note = pending.feasibility_note || "";
    const artisanMatch = note.match(/Artisan\s+([A-Za-z\s]+?)\s+specialty/);
    const backlogMatch = note.match(/backlog\s+(\d+)d/);
    const baseFabMatch = note.match(/Base\s+fab:\s+(\d+)d/);
    const qcBufferMatch = note.match(/QC\s+buffer:\s+(\d+)d/);
    
    const artisanName = artisanMatch ? artisanMatch[1].trim() : "Unassigned";
    const backlogVal = backlogMatch ? `${backlogMatch[1]} days` : "0 days";
    
    let timelineDays = 0;
    if (baseFabMatch) timelineDays += parseInt(baseFabMatch[1]);
    if (qcBufferMatch) timelineDays += parseInt(qcBufferMatch[1]);
    
    document.getElementById('mbadgeArtisanVal').textContent = artisanName;
    document.getElementById('mbadgeBacklogVal').textContent = backlogVal;
    
    // Status color overrides for production indicators
    const isFeasible = pending.estimated_days <= pending.deadline_days;
    const timelineBadge = document.getElementById('mbadgeTimeline');
    timelineBadge.classList.remove('status-green', 'status-amber', 'status-red');
    if (isFeasible) {
      timelineBadge.classList.add('status-green');
    } else {
      timelineBadge.classList.add('status-red');
    }
    document.getElementById('mbadgeTimelineVal').innerHTML = `<strong>${pending.estimated_days} days</strong>`;
    
    const backlogDays = backlogMatch ? parseInt(backlogMatch[1]) : 0;
    const backlogBadge = document.getElementById('mbadgeBacklog');
    backlogBadge.classList.remove('status-green', 'status-amber', 'status-red');
    if (backlogDays === 0) {
      backlogBadge.classList.add('status-green');
    } else if (backlogDays < 5) {
      backlogBadge.classList.add('status-amber');
    } else {
      backlogBadge.classList.add('status-red');
    }
    
    // Populate pricing compare using renderCostBreakdown
    const breakdown = renderCostBreakdown(pending);
    drawerProposedVal.textContent = breakdown.salesQuoteUSD;
    drawerTrueCostVal.textContent = breakdown.trueCostUSD;
    drawerSuggestedVal.textContent = breakdown.suggestedPriceUSD;
    
    // Populate adjacent Display and Input
    document.getElementById('drawerSuggestedValDisplay').textContent = breakdown.suggestedPriceUSD;
    
    // Pre-fill Adjusted Price field with Sales agent's proposed price as visual anchor
    overrideAdjustedPrice.value = pending.proposed_price.toFixed(2);
    
    currentSuggestedPrice = pending.suggested_price;
    updatePriceComparisonStatus(currentSuggestedPrice);
    
    // Attach listener for price dynamic changes
    overrideAdjustedPrice.oninput = () => {
      updatePriceComparisonStatus(currentSuggestedPrice);
    };
    
    // Reset justification reason chips
    document.querySelectorAll('#overrideReasonChips .chip-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById('overrideOptionalNote').value = '';
    document.getElementById('overrideMemo').value = '';
    
    // Render negotiation log bubbles
    const logContainer = document.getElementById('drawerNegotiationLog');
    if (logContainer) {
      logContainer.innerHTML = '';
      const log = pending.negotiation_log || [];
      if (log.length === 0) {
        logContainer.innerHTML = '<div class="light-text" style="font-size: 0.7rem; text-align: center;">No negotiation log available.</div>';
      } else {
        log.forEach(turn => {
          const bubble = document.createElement('div');
          
          // Class based on turn properties
          bubble.className = `negotiation-bubble agent-${turn.agent.toLowerCase()} turn-${turn.turn_type}`;
          if (turn.agent === 'System' || turn.turn_type === 'cap_hit') {
            bubble.className = `negotiation-bubble turn-system-cap_hit`;
          } else if (turn.turn_type === 'fallback') {
            bubble.className = `negotiation-bubble turn-fallback`;
          }
          
          // Format timestamp nicely
          let timeStr = "";
          if (turn.timestamp) {
            try {
              const dt = new Date(turn.timestamp);
              timeStr = dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            } catch (e) {
              timeStr = turn.timestamp;
            }
          }
          
          bubble.innerHTML = `
            <div class="bubble-meta">
              <span>${turn.agent} (${turn.turn_type.toUpperCase()}) - Round ${turn.round}</span>
              <span class="bubble-time">${timeStr}</span>
            </div>
            <div class="bubble-text">${escapeHTML(turn.text)}</div>
          `;
          logContainer.appendChild(bubble);
        });
        // Auto-scroll to the bottom of the container
        logContainer.scrollTop = logContainer.scrollHeight;
      }
    }
    
  } else {
    // Close drawer
    approvalDrawer.classList.remove('active');
    currentPendingId = null;
  }
}

// Handle override drawer approval/rejection submission
function handleOverrideDecision(decision) {
  const selectedChips = Array.from(document.querySelectorAll('#overrideReasonChips .chip-btn.active')).map(btn => btn.dataset.val);
  const optionalNote = document.getElementById('overrideOptionalNote').value.trim();
  
  if (decision === 'approve' && selectedChips.length === 0 && !optionalNote) {
    alert("An operator override reason justification selection is required before execution.");
    return;
  }
  
  let memoText = "";
  if (decision === 'approve') {
    const chips_str = selectedChips.join(', ');
    memoText = `Chips: [${chips_str}]`;
    if (optionalNote) {
      memoText += ` | Note: ${optionalNote}`;
    }
    document.getElementById('overrideMemo').value = memoText;
  } else {
    memoText = optionalNote || "Rejected by Operator Override Gate";
    document.getElementById('overrideMemo').value = memoText;
  }
  
  const payload = {
    decision: decision,
    adjusted_price: parseFloat(overrideAdjustedPrice.value),
    memo: decision === 'approve' ? {
      chips: selectedChips,
      note: optionalNote
    } : memoText
  };
  
  // Disable drawer actions
  drawerApproveBtn.disabled = true;
  drawerRejectBtn.disabled = true;
  
  fetch('/api/override', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(res => {
    // Clear graph visualizer overriding nodes to normal
    setNodeState('override', decision === 'approve' ? 'success' : 'blocked');
    setEdgeState('override-orchestrator', 'active');
    setNodeState('orchestrator', 'processing');
    
    setTimeout(() => {
      setNodeState('orchestrator', decision === 'approve' ? 'success' : 'blocked');
      setEdgeState('orchestrator-ledger', 'active');
      
      // Close drawer and reset state
      approvalDrawer.classList.remove('active');
      currentPendingId = null;
      drawerApproveBtn.disabled = false;
      drawerRejectBtn.disabled = false;
      
      fetchDashboardState();
    }, 600);
  })
  .catch(err => {
    console.error("Override submission failed:", err);
    drawerApproveBtn.disabled = false;
    drawerRejectBtn.disabled = false;
    alert("Error occurred executing override.");
  });
}

// Update Ledger list table
let localLedgerCache = [];
function updateLedgerTable(ledger) {
  localLedgerCache = ledger;
  refreshLedgerTable();
}

function refreshLedgerTable() {
  ledgerBody.innerHTML = '';
  
  if (localLedgerCache.length === 0) {
    const row = document.createElement('tr');
    row.innerHTML = `<td colspan="13" class="light-text" style="text-align: center; padding: 2rem;">No orders currently logged in the ledger. Use the Intake Panel to begin.</td>`;
    ledgerBody.appendChild(row);
    return;
  }
  
  const isUSD = currentCurrency === 'USD';
  const symb = isUSD ? '$' : '₹';
  const mult = isUSD ? 1.0 : (currentSpot.usd_inr || 84.0);
  
  localLedgerCache.forEach(row => {
    const tr = document.createElement('tr');
    
    // Choose pathway styling
    let pathwayClass = 'auto';
    if (row.resolution_pathway === 'Human Approved') pathwayClass = 'approved';
    if (row.resolution_pathway === 'Human Rejected') pathwayClass = 'rejected';
    
    const finalPrice = row.final_price * mult;
    const salesQuote = row.sales_quote * mult;
    const trueCost = row.true_cost * mult;
    const metalRate = row.live_metal_rate * mult;
    
    tr.innerHTML = `
      <td class="font-mono">${row.order_id}</td>
      <td class="light-text">${row.timestamp}</td>
      <td><strong>${row.customer_name}</strong></td>
      <td class="light-text">${row.details}</td>
      <td class="font-mono">${symb}${salesQuote.toFixed(2)}</td>
      <td class="font-mono"><strong>${symb}${finalPrice.toFixed(2)}</strong></td>
      <td class="font-mono">${symb}${trueCost.toFixed(2)}</td>
      <td class="font-mono ${row.net_margin < 15 ? 'text-danger' : 'text-success'}">${row.net_margin}%</td>
      <td class="font-mono">${symb}${metalRate.toFixed(2)}</td>
      <td class="font-mono">₹${(row.final_price * (currentSpot.usd_inr || 84.0)).toFixed(2)}</td>
      <td class="light-text font-mono" style="font-size: 0.7rem;">${row.trust_score_changes}</td>
      <td><span class="pathway-badge ${pathwayClass}">${row.resolution_pathway}</span></td>
      <td><span class="light-text">${row.approval_memo}</span></td>
    `;
    ledgerBody.appendChild(tr);
  });
}

// Draw CAD blueprint vector SVG paths with styling and animation
function drawCADBlueprint() {
  const drawGroup = document.getElementById('blueprintDrawings');
  if (!drawGroup) return;
  drawGroup.innerHTML = '';
  
  let m, k, w, t, template;
  if (activeTab === 'tab-standard') {
    m = selectedMetal;
    k = selectedPurity;
    w = parseFloat(document.getElementById('stdWeightG').value) || 0;
    t = document.getElementById('stdTechnique').value;
    template = selectedTemplate;
  } else {
    m = document.getElementById('custMetalType').value;
    k = document.getElementById('custKaratPurity').value;
    w = parseFloat(document.getElementById('custWeightG').value) || 0;
    t = document.getElementById('custTechnique').value;
    template = 'custom';
  }
  
  // Update texts overlays
  document.getElementById('bpSpecMetal').textContent = `METAL: ${m.toUpperCase()} (${k.toUpperCase()})`;
  document.getElementById('bpSpecWeight').textContent = `WEIGHT: ${w.toFixed(2)} g`;
  document.getElementById('bpSpecTechnique').textContent = `TECHNIQUE: ${t.toUpperCase()}`;
  
  // Decide design layout: Ring, Necklace/Pendant, or Bracelet
  const isRing = template.includes('Ring') || template === 'Classic Solitaire Engagement Ring' || t === 'stone-setting';
  const isNecklace = template.includes('Set') || template === 'Royal Filigree Bridal Set' || t === 'filigree';
  
  if (isRing) {
    // Ring drawing: Concentric circles band at center (150, 120)
    // Outer circle
    const c1 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c1.setAttribute('cx', '150');
    c1.setAttribute('cy', '130');
    c1.setAttribute('r', '40');
    c1.className.baseVal = 'blueprint-path';
    drawGroup.appendChild(c1);
    
    // Inner circle
    const c2 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c2.setAttribute('cx', '150');
    c2.setAttribute('cy', '130');
    c2.setAttribute('r', '34');
    c2.className.baseVal = 'blueprint-path';
    drawGroup.appendChild(c2);
    
    // Dimension lines
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', '110');
    line.setAttribute('y1', '130');
    line.setAttribute('x2', '190');
    line.setAttribute('y2', '130');
    line.className.baseVal = 'blueprint-dim';
    drawGroup.appendChild(line);
    
    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('x', '150');
    txt.setAttribute('y', '125');
    txt.setAttribute('text-anchor', 'middle');
    txt.className.baseVal = 'blueprint-text';
    txt.textContent = 'Ø 18.5mm';
    drawGroup.appendChild(txt);
    
    // Draw top stone (solitaire setting) if template is solitaire or weight > 8
    if (w > 8 || template === 'Classic Solitaire Engagement Ring' || t === 'stone-setting') {
      const stone = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
      // diamond facets centered at 150, 85
      stone.setAttribute('points', '136,90 164,90 172,76 150,55 128,76');
      stone.className.baseVal = 'blueprint-path';
      drawGroup.appendChild(stone);
      
      const prongs = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      prongs.setAttribute('d', 'M 134 90 L 140 100 M 166 90 L 160 100');
      prongs.className.baseVal = 'blueprint-path';
      drawGroup.appendChild(prongs);
    }
  } else if (isNecklace) {
    // Necklace / filigree pendant drawing
    // Curved necklace collar path
    const collar = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    collar.setAttribute('d', 'M 80 60 Q 150 140 220 60');
    collar.className.baseVal = 'blueprint-path';
    drawGroup.appendChild(collar);
    
    // Ornate filigree drop pendant centered at 150, 110
    const pendant = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    pendant.setAttribute('d', 'M 150 100 C 130 120 130 160 150 180 C 170 160 170 120 150 100 Z');
    pendant.className.baseVal = 'blueprint-path';
    drawGroup.appendChild(pendant);
    
    // Interior filigree scrolls
    const scrolls = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    scrolls.setAttribute('d', 'M 150 115 Q 140 135 150 150 Q 160 135 150 115 M 150 150 Q 145 160 150 170 Q 155 160 150 150');
    scrolls.className.baseVal = 'blueprint-path';
    drawGroup.appendChild(scrolls);
    
    // Dimension line
    const dim = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    dim.setAttribute('d', 'M 80 50 L 220 50');
    dim.className.baseVal = 'blueprint-dim';
    drawGroup.appendChild(dim);
    
    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('x', '150');
    txt.setAttribute('y', '45');
    txt.setAttribute('text-anchor', 'middle');
    txt.className.baseVal = 'blueprint-text';
    txt.textContent = '420mm COLLAR LENGTH';
    drawGroup.appendChild(txt);
  } else {
    // Kada Bangle / Bracelet ellipse drawing
    const b1 = document.createElementNS('http://www.w3.org/2000/svg', 'ellipse');
    b1.setAttribute('cx', '150');
    b1.setAttribute('cy', '125');
    b1.setAttribute('rx', '70');
    b1.setAttribute('ry', '40');
    b1.className.baseVal = 'blueprint-path';
    drawGroup.appendChild(b1);
    
    const b2 = document.createElementNS('http://www.w3.org/2000/svg', 'ellipse');
    b2.setAttribute('cx', '150');
    b2.setAttribute('cy', '125');
    b2.setAttribute('rx', '64');
    b2.setAttribute('ry', '34');
    b2.className.baseVal = 'blueprint-path';
    drawGroup.appendChild(b2);
    
    // Bangle engraving or polishing details
    const det = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    det.setAttribute('d', 'M 80 125 L 85 120 M 220 125 L 215 130 M 150 85 L 155 90 M 150 165 L 145 160');
    det.className.baseVal = 'blueprint-path';
    drawGroup.appendChild(det);
    
    // Dimension line
    const dim = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    dim.setAttribute('x1', '80');
    dim.setAttribute('y1', '125');
    dim.setAttribute('x2', '220');
    dim.setAttribute('y2', '125');
    dim.className.baseVal = 'blueprint-dim';
    drawGroup.appendChild(dim);
    
    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('x', '150');
    txt.setAttribute('y', '120');
    txt.setAttribute('text-anchor', 'middle');
    txt.className.baseVal = 'blueprint-text';
    txt.textContent = '62mm INNER DIAM';
    drawGroup.appendChild(txt);
  }
}

// Helpers
function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function escapeHTML(str) {
  return str.replace(/[&<>'"]/g, 
    tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag)
  );
}

function renderCostBreakdown(order) {
  const mult = currentCurrency === 'USD' ? 1.0 : (currentSpot.usd_inr || 84.0);
  const symb = currentCurrency === 'USD' ? '$' : '₹';
  
  const finalPrice = order.final_price !== undefined ? order.final_price : (order.proposed_price || 0.0);
  const trueCost = order.true_cost || 0.0;
  const suggestedPrice = order.suggested_price !== undefined ? order.suggested_price : (trueCost / 0.85);
  const salesQuote = order.sales_quote !== undefined ? order.sales_quote : (order.proposed_price || 0.0);
  
  let liveMetalRate = order.live_metal_rate;
  if (liveMetalRate === undefined) {
    const metal = order.metal || 'Gold';
    liveMetalRate = metal.toLowerCase() === 'gold' ? currentSpot.gold_usd_g : currentSpot.silver_usd_g;
    if (order.karat_or_purity) {
      let purityRatio = 1.0;
      if (metal.toLowerCase() === 'gold') {
        const karat = parseFloat(order.karat_or_purity.replace(/[^0-9.]/g, '')) || 22.0;
        purityRatio = karat / 24.0;
      } else {
        if (order.karat_or_purity.includes('92.5')) purityRatio = 0.925;
      }
      liveMetalRate = liveMetalRate * purityRatio;
    }
  }

  const details = order.details || `${order.weight_g}g ${order.karat_or_purity} ${order.metal} (${order.complexity}) | Gem: ${order.gemstone} | Size: ${order.size} | Finish: ${order.finish}`;
  const gemMatch = details.match(/Gem:\s*([A-Za-z]+)/);
  const gemVal = gemMatch ? gemMatch[1] : (order.gemstone || "None");

  return {
    finalPriceUSD: `$${finalPrice.toFixed(2)}`,
    finalPriceConverted: `${symb}${(finalPrice * mult).toFixed(2)}`,
    trueCostUSD: `$${trueCost.toFixed(2)}`,
    trueCostConverted: `${symb}${(trueCost * mult).toFixed(2)}`,
    suggestedPriceUSD: `$${suggestedPrice.toFixed(2)}`,
    suggestedPriceConverted: `${symb}${(suggestedPrice * mult).toFixed(2)}`,
    salesQuoteUSD: `$${salesQuote.toFixed(2)}`,
    salesQuoteConverted: `${symb}${(salesQuote * mult).toFixed(2)}`,
    liveMetalRateConverted: `${symb}${(liveMetalRate * mult).toFixed(2)}`,
    gemVal: gemVal,
    hasGem: gemVal !== "None"
  };
}

