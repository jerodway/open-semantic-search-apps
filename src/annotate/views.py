from django.shortcuts import render
from django.urls import reverse
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.template import RequestContext
from django.forms import ModelForm
from django.views import generic
import django.forms as forms

from opensemanticetl.etl import ETL

import json
import urllib
from rdflib import Graph, Literal, BNode, Namespace, RDF, URIRef

from annotate.models import Annotation
from thesaurus.models import Concept
from thesaurus.models import Facet

# apply annotations to search index
def export_to_index(uri):

	etl = ETL()

	# plugin enhance_annotations reads the tags and annotations
	# plugin enhance_multilingual copies them to default search fields
	etl.config['plugins'] = ['enhance_annotations','enhance_multilingual']

	# if something went wrong, raise exception to UI
	etl.config['raise_pluginexception'] = True

	parameters = etl.config.copy()

	# since we only enrich and not ETL the document/analysis pipeline again, text(s) has to be added to default search fields, not overwrite existing text
	parameters['add'] = True

	# but the (maybe changed) notes should overwrite existing comments
	# and some ETL process metadata in etl_* single value fields can not be added,
	# so overwrite them, too
	parameters['fields_set'] = [
		'notes_txt',
		'etl_time_millis_i',
		'etl_enhance_annotations_b',
		'etl_enhance_annotations_time_millis_i',
		'etl_enhance_multilingual_b',
		'etl_enhance_multilingual_time_millis_i'
	]

	parameters['id'] = uri

	etl.process (parameters=parameters, data={})
	etl.commit()


class AnnotationForm(ModelForm):

	tags = forms.ModelMultipleChoiceField(queryset=Concept.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)

	class Meta:
		model = Annotation
		fields = '__all__'


class IndexView(generic.ListView):
	model = Annotation

class DetailView(generic.DetailView):
	model = Annotation

class UpdateView(generic.UpdateView):
	model = Annotation
	form_class = AnnotationForm


def update_annotation(request, id):
	instance = MyModel.objects.get(id=id)
	form = MyForm(request.POST or None, instance=instance)
	if form.is_valid():
		form.save()
		return redirect('next_view')


def update_annotation(request, pk):

	annotation = Annotation.objects.get(pk=pk)

	if request.method == 'POST':
		form = AnnotationForm(request.POST, request.FILES, instance=annotation)
		if form.is_valid():
			annotation = form.save()

			# apply new data to search index
			export_to_index(annotation.uri)

			return HttpResponseRedirect( reverse('annotate:detail', args=[annotation.pk])) # Redirect after POST

	else:
		form = AnnotationForm(instance=annotation)


	return render(request, 'annotate/annotation_form.html',
				  {'form': form, } )






def create_annotation(request):

	if request.method == 'POST':
		form = AnnotationForm(request.POST, request.FILES)
		if form.is_valid():
			annotation = form.save()

			# apply new data to search index
			export_to_index(annotation.uri)

			return HttpResponseRedirect( reverse('annotate:detail', args=[annotation.pk])) # Redirect after POST

	else:

		if 'uri' in request.GET:
			initials = {
				"uri": request.GET['uri']
			}
			form = AnnotationForm(initial=initials)
		else:
			form = AnnotationForm()


	return render(request, 'annotate/annotation_form.html',
				  {'form': form, } )



def edit_annotation(request):

	uri = request.GET['uri']

	annotations = Annotation.objects.filter(uri=uri)

	if annotations:

		# get first primary key of annotation with given uri
		pk = annotations[0].pk
		annotation = Annotation.objects.get(pk=pk)

		#todo: warning message if more (if racing condition on creation)

		# redirect to edit this annotation
		return HttpResponseRedirect( reverse('annotate:update', args=[pk])) # Redirect after POST

	else:
		# no annotation for that uri, so redirect to create view
		return HttpResponseRedirect( "{}?uri={}".format( reverse('annotate:create'), urllib.parse.quote_plus( uri ) ) ) # Redirect after POST



# serialize annotations for uri to JSON
def export_json(request):

	uri = request.GET['uri']

	data = {}

	annotations = Annotation.objects.filter(uri=uri)

	for annotation in annotations:

		if annotation.title:
			data['title_txt'] = annotation.title

		if annotation.notes:
			data['notes_txt'] = annotation.notes

		for tag in annotation.tags.all():
			facet = "tag_ss"
			if tag.facet:
				facet = tag.facet.facet
			if not facet in data:
				data[facet] = []
			data[facet].append(tag.prefLabel)

	return HttpResponse(json.dumps(data), content_type="application/json")


# serialize annotations for uri to RDF graph
def export_rdf(request):

	uri = request.GET['uri']

	g = Graph()

	annotations = Annotation.objects.filter(uri=uri)

	for annotation in annotations:

		if annotation.title:
			g.add( ( URIRef(annotation.uri), URIRef("http://schema.org/title"), Literal(annotation.title) ) )

		if annotation.notes:
			g.add( ( URIRef(annotation.uri), URIRef("http://schema.org/Comment"), Literal(annotation.notes) ) )

		for tag in annotation.tags.all():
			facet_property = 'http://schema.org/keywords'
			if tag.facet:
				if tag.facet.uri:
					facet_property = tag.facet.uri
			g.add( ( URIRef(annotation.uri), URIRef(facet_property), Literal(tag.prefLabel) ) )

	status = HttpResponse(g.serialize( format='xml' ) )
	status["Content-Type"] = "application/rdf+xml"
	return status
