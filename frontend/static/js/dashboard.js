// Dashboard JavaScript functionality

// Global variable to track selected slice
let selectedSliceRow = null;

// Function to delete a slice with confirmation
function deleteSlice(sliceId, sliceName) {
    if (confirm(`¿Está seguro de que desea eliminar "${sliceName}"?\n\nEsta acción no se puede deshacer.`)) {
        fetch(`/delete_slice/${sliceId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Show success message
                showAlert('success', data.message);
                // Reload page to update the table
                setTimeout(() => {
                    window.location.reload();
                }, 1500);
            } else {
                showAlert('danger', data.error || 'Error eliminando el slice');
            }
        })
        .catch(error => {
            console.error('Error deleting slice:', error);
            showAlert('danger', 'Error de conexión eliminando el slice');
        });
    }
}

// Function to show alert messages
function showAlert(type, message) {
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    // Find the content area and prepend the alert
    const contentCard = document.querySelector('.content-card');
    if (contentCard) {
        contentCard.insertAdjacentHTML('beforebegin', alertHtml);
    }
}

// Function to select a slice and show its details
function selectSlice(sliceId) {
    // Remove previous selection
    if (selectedSliceRow) {
        selectedSliceRow.classList.remove('selected');
    }
    
    // Add selection to current row
    const clickedRow = event.currentTarget;
    clickedRow.classList.add('selected');
    selectedSliceRow = clickedRow;
    
    // Fetch slice details
    fetch(`/slice/${sliceId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            showSliceDetails(data);
        })
        .catch(error => {
            console.error('Error fetching slice details:', error);
            alert('Error loading slice details');
        });
}

// Function to display slice details
function showSliceDetails(slice) {
    // Populate detail fields
    document.getElementById('detailId').textContent = slice.id;
    document.getElementById('detailEstado').textContent = slice.estado;
    document.getElementById('detailCreated').textContent = slice.fecha_creacion;
    document.getElementById('detailOwner').textContent = slice.owner;
    document.getElementById('detailInstances').textContent = `${slice.instances.length} VM(s)`;
    
    // Apply status styling
    const statusElement = document.getElementById('detailEstado');
    statusElement.className = `status-badge ${slice.estado === 'RUNNING' ? 'status-running' : 'status-stopped'}`;
    
    // Update topology view link
    const topologyLink = document.getElementById('viewTopologyLink');
    topologyLink.href = `/slice/${slice.id}/topology`;
    
    // Show instances list
    const instancesList = document.getElementById('instancesList');
    instancesList.innerHTML = '';
    
    if (slice.instances && slice.instances.length > 0) {
        const instancesTitle = document.createElement('div');
        instancesTitle.innerHTML = '<h6><i class="fas fa-server me-2"></i>Instancias:</h6>';
        instancesList.appendChild(instancesTitle);
        
        slice.instances.forEach(instance => {
            const instanceCard = document.createElement('div');
            instanceCard.className = 'col-md-6 mb-2';
            instanceCard.innerHTML = `
                <div class="card card-sm">
                    <div class="card-body p-2">
                        <h6 class="card-title mb-1">${instance.nombre}</h6>
                        <small class="text-muted">
                            CPU: ${instance.cpu} | RAM: ${instance.ram} | Storage: ${instance.storage}
                            <br>Imagen: ${instance.imagen}
                        </small>
                    </div>
                </div>
            `;
            instancesList.appendChild(instanceCard);
        });
    }
    
    // Show the details panel
    document.getElementById('sliceDetails').style.display = 'block';
    
    // Scroll to details panel
    document.getElementById('sliceDetails').scrollIntoView({ 
        behavior: 'smooth',
        block: 'start'
    });
}

// Add click event listeners to slice links
document.addEventListener('DOMContentLoaded', function() {
    // Prevent default link behavior for slice links
    const sliceLinks = document.querySelectorAll('.slice-link');
    sliceLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const sliceId = this.getAttribute('data-slice-id');
            selectSlice(sliceId);
        });
    });
});