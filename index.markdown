---
layout: default
title: Driftless Trout Fishing Trip Log
---

<style>
.post-card {
  display: flex;
  flex-direction: row;
  margin-bottom: 2rem;
  border-bottom: 1px solid #eee;
  padding-bottom: 2rem;
  gap: 1.5rem;
  align-items: flex-start;
}
.post-card__thumb {
  flex: 0 0 200px;
  padding-top: 2.2rem;
}
.post-card__thumb img {
  width: 200px;
  height: 200px;
  object-fit: cover;
  object-position: center;
  border-radius: 4px;
}
.post-card__body {
  flex: 1;
  padding-top: 0.5rem;
}
.post-card__map {
  flex: 0 0 200px;
  padding-top: 2.2rem;
}
.mini-map {
  height: 200px;
  border-radius: 4px;
  border: 1px solid #ddd;
}
@media (max-width: 640px) {
  .post-card {
    flex-direction: column;
    gap: 0;
    padding-left: 0;
    padding-right: 0;
    padding-bottom: 1.5rem;
  }
  .post-card__thumb {
    flex: none;
    width: calc(100% + 2rem);
    margin-left: -1rem;
    margin-bottom: 0.75rem;
    padding-top: 0;
  }
  .post-card__thumb img {
    width: 100%;
    height: 220px;
    border-radius: 0;
  }
  .post-card__body {
    padding: 0 0.25rem;
  }
  .post-card__map {
    display: none;
  }
}
.cost-badge {
  position: relative;
  cursor: default;
  user-select: none;
}
.cost-tooltip {
  display: none;
  position: absolute;
  bottom: calc(100% + 10px);
  left: 0;
  background: #f0ebe0;
  border-radius: 6px;
  padding: 0.6rem 0.85rem;
  min-width: 170px;
  z-index: 100;
  font-size: 0.8rem;
  color: #333;
  flex-direction: column;
  gap: 0.2rem;
  pointer-events: none;
  box-shadow: 0 4px 18px rgba(0,0,0,0.22);
}
.cost-tooltip::after {
  content: '';
  position: absolute;
  bottom: -7px;
  left: 12px;
  width: 12px;
  height: 12px;
  background: #f0ebe0;
  transform: rotate(45deg);
  box-shadow: 3px 3px 6px rgba(0,0,0,0.1);
}
.cost-row {
  display: flex;
  justify-content: space-between;
  gap: 1.5rem;
}
.cost-total {
  border-top: 1px solid #d8d2c6;
  margin-top: 0.1rem;
  padding-top: 0.3rem;
  font-weight: 600;
  color: #05bf85;
}
.cost-badge:hover .cost-tooltip,
.cost-badge.open .cost-tooltip {
  display: flex;
}
.cost-badge:focus {
  outline: none;
}
</style>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<div style="width: 100vw; position: relative; left: 50%; right: 50%; margin-left: -50vw; margin-right: -50vw; height: 300px; background-image: url('/assets/images/banner.jpg'); background-size: cover; background-position: center; display: flex; align-items: center; justify-content: center; margin-bottom: 3rem;">
  <div style="background: rgba(0,0,0,0.45); padding: 2rem 3rem; text-align: center;">
    <h1 style="color: white; margin: 0; font-size: 2.5rem;">DeVrou Trout Fishing</h1>
    <p style="color: #ddd; margin: 0.5rem 0 0;">A personal log of Trout Fishing Trips</p>
  </div>
</div>

<div style="max-width: 1100px; margin: 0 auto;">
{% for post in site.posts %}
{% assign has_coords = false %}
{% for day in post.days %}{% for spot in day.spots %}{% if spot.lat %}{% assign has_coords = true %}{% endif %}{% endfor %}{% endfor %}
{% if post.campsite.lat %}{% assign has_coords = true %}{% endif %}
<div class="post-card">
  {% if post.images %}
  <div class="post-card__thumb">
    <a href="{{ post.url }}">
      <img src="{{ post.thumbnail | default: post.images[0] }}" alt="{{ post.title }}">
    </a>
  </div>
  {% endif %}
  <div class="post-card__body">
    <h3 style="margin: 0 0 0.1rem;"><a href="{{ post.url }}">{{ post.title }}</a></h3>
    <small style="display: block; margin: 0;">{{ post.date | date: "%B %d, %Y" }}</small>
    {% if post.summary %}
    <p style="margin: 0.05rem 0 0; color: #666; font-size: 0.9rem; line-height: 1.4;">{{ post.summary }}</p>
    {% endif %}
    {% if post.days or post.campsite.name or post.cost or post.youtube %}
    <div style="margin-top: 0.75rem; display: flex; flex-wrap: wrap; gap: 0.4rem;">
      {% if post.days %}
      <span style="font-size: 0.78rem; background: #f0ebe0; padding: 0.2rem 0.6rem; border-radius: 4px; color: #555; border-left: 3px solid #2596be;">{{ post.days | size }} days</span>
      {% endif %}
      {% if post.campsite.name %}
      {% if post.campsite.url %}
      <a href="{{ post.campsite.url }}" target="_blank" rel="noopener" style="font-size: 0.78rem; background: #f0ebe0; padding: 0.2rem 0.6rem; border-radius: 4px; color: #555; border-left: 3px solid #39b831; text-decoration: none;">{{ post.campsite.name }}</a>
      {% else %}
      <span style="font-size: 0.78rem; background: #f0ebe0; padding: 0.2rem 0.6rem; border-radius: 4px; color: #555; border-left: 3px solid #39b831;">{{ post.campsite.name }}</span>
      {% endif %}
      {% endif %}
      {% if post.cost %}
      {% assign total = 0 %}
      {% for item in post.cost.items %}{% assign total = total | plus: item.amount %}{% endfor %}
      <span class="cost-badge" tabindex="0" style="font-size: 0.78rem; background: #f0ebe0; padding: 0.2rem 0.6rem; border-radius: 4px; color: #555; border-left: 3px solid #05bf85;">
        ${{ total }}
        <span class="cost-tooltip">{% for item in post.cost.items %}<span class="cost-row"><span>{{ item.name }}</span><span>${{ item.amount }}</span></span>{% endfor %}<span class="cost-row cost-total"><span>Total</span><span>${{ total }}</span></span></span>
      </span>
      {% endif %}
      {% if post.youtube %}
      <a href="{{ post.youtube[0].url }}" target="_blank" rel="noopener" style="font-size: 0.78rem; background: #cc2c3f; padding: 0.2rem 0.6rem; border-radius: 4px; color: white; text-decoration: none;">YouTube</a>
      {% endif %}
    </div>
    {% endif %}
  </div>
  {% if has_coords %}
  <div class="post-card__map">
    <div id="mini-map-{{ forloop.index }}" class="mini-map"></div>
  </div>
  {% endif %}
</div>
{% if has_coords %}
<script>
(function() {
  var map = L.map('mini-map-{{ forloop.index }}', {
    zoomControl: false,
    dragging: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    touchZoom: false,
    attributionControl: false
  });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
  var dayColors = ['#2596be','#cc2c3f','#cc852b','#ccc62b','#9b29cb'];
  var bounds = [];
  {% if post.campsite.lat %}
  L.circleMarker([{{ post.campsite.lat }}, {{ post.campsite.lng }}], { radius: 6, color: '#39b831', fillColor: '#39b831', fillOpacity: 0.9, weight: 1.5 }).addTo(map);
  bounds.push([{{ post.campsite.lat }}, {{ post.campsite.lng }}]);
  {% endif %}
  {% for day in post.days %}{% assign di = forloop.index0 %}{% for spot in day.spots %}{% if spot.lat %}
  L.circleMarker([{{ spot.lat }}, {{ spot.lng }}], { radius: 5, color: dayColors[{{ di }}], fillColor: dayColors[{{ di }}], fillOpacity: 0.85, weight: 1.5 }).addTo(map);
  bounds.push([{{ spot.lat }}, {{ spot.lng }}]);
  {% endif %}{% endfor %}{% endfor %}
  if (bounds.length > 0) map.fitBounds(bounds, { padding: [12, 12] });
})();
</script>
{% endif %}
{% endfor %}
</div>
<script>
if (!window.matchMedia('(hover: hover)').matches) {
  document.querySelectorAll('.cost-badge').forEach(function(badge) {
    badge.addEventListener('click', function(e) {
      e.stopPropagation();
      badge.classList.toggle('open');
    });
  });
  document.addEventListener('click', function() {
    document.querySelectorAll('.cost-badge.open').forEach(function(b) { b.classList.remove('open'); });
  });
}
</script>
