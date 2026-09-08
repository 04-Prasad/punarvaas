/** Deployment configuration: replace endpoints/attribution with your tile provider. */
export const BASEMAPS = {
  satellite: {
    label: 'Satellite',
    layers: [{
      url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      attribution: 'Imagery © <a href="https://www.esri.com/">Esri</a>, Vantor, Earthstar Geographics, GIS User Community',
      maxNativeZoom: 18,
    }, {
      url: 'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
      attribution: 'Labels © Esri, HERE, Garmin, OpenStreetMap contributors, GIS User Community',
      maxNativeZoom: 18, labels: true,
    }],
  },
  streets: {
    label: 'Streets',
    layers: [{ url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>', maxNativeZoom: 19 }],
  },
  none: { label: 'Zones only', layers: [] },
};
