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
  align-items: center;
}
.post-card__thumb {
  flex: 0 0 200px;
}
.post-card__thumb img {
  width: 200px;
  height: 200px;
  object-fit: cover;
  object-position: center;
  border-radius: 4px;
}
.post-card__body {
  padding: 0;
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
  }
  .post-card__thumb img {
    width: 100%;
    height: 220px;
    border-radius: 0;
  }
  .post-card__body {
    padding: 0 0.25rem;
  }
}
</style>

<div style="width: 100vw; position: relative; left: 50%; right: 50%; margin-left: -50vw; margin-right: -50vw; height: 300px; background-image: url('/assets/images/banner.jpg'); background-size: cover; background-position: center; display: flex; align-items: center; justify-content: center; margin-bottom: 3rem;">
  <div style="background: rgba(0,0,0,0.45); padding: 2rem 3rem; text-align: center;">
    <h1 style="color: white; margin: 0; font-size: 2.5rem;">DeVrou Trout Fishing</h1>
    <p style="color: #ddd; margin: 0.5rem 0 0;">A personal log of Trout Fishing Trips</p>
  </div>
</div>

<div style="max-width: 900px; margin: 0 auto;">
{% for post in site.posts %}
<div class="post-card">
  {% if post.images %}
  <div class="post-card__thumb">
    <a href="{{ post.url }}">
      <img src="{{ post.thumbnail | default: post.images[0] }}" alt="{{ post.title }}">
    </a>
  </div>
  {% endif %}
  <div class="post-card__body">
    <h3 style="margin-bottom: 0.25rem;"><a href="{{ post.url }}">{{ post.title }}</a></h3>
    <small>{{ post.date | date: "%B %d, %Y" }}</small>
    {% if post.summary %}
    <p style="margin: 0.5rem 0 0; color: #666; font-size: 0.9rem;">{{ post.summary }}</p>
    {% endif %}
  </div>
</div>
{% endfor %}
</div>