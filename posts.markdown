---
layout: default
title: Posts
permalink: /posts
---

{% for post in site.posts %}
<div style="margin-bottom: 1.5rem; border-bottom: 1px solid #eee; padding-bottom: 1rem;">
  <h3><a href="{{ post.url }}">{{ post.title }}</a></h3>
  <small>{{ post.date | date: "%B %d, %Y" }}</small>
</div>
{% endfor %}