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
      <span style="font-size: 0.78rem; background: #f0ebe0; padding: 0.2rem 0.6rem; border-radius: 4px; color: #555; border-left: 3px solid #39b831;">{{ post.campsite.name }}</span>
      {% endif %}
      {% if post.cost %}
      {% assign total = 0 %}
      {% for item in post.cost.items %}{% assign total = total | plus: item.amount %}{% endfor %}
      <span style="font-size: 0.78rem; background: #f0ebe0; padding: 0.2rem 0.6rem; border-radius: 4px; color: #555; border-left: 3px solid #05bf85;">${{ total }}</span>
      {% endif %}
      {% if post.youtube %}
      <span style="font-size: 0.78rem; background: #cc2c3f; padding: 0.2rem 0.6rem; border-radius: 4px; color: white;">YouTube</span>
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
