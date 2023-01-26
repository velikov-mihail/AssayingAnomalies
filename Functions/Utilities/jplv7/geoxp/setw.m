% Callback function for the slider created in morancontiplotmap.m
% Not usable outside this context
%-----------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr-

global Hslide;
global Htw;
global vglob;
global mat;
global seuil;
global lat;
global long;
global WX;
global stdvar;
global Iloc;
global Imoran;
global Ht;
global reg;
global Q1;
global Q2;
global Q3;
global Q4;
global stdvar;
global pvalue;
global Ht2;

seuil=get(Hslide,'Value');
set(Htw,'String',num2str(seuil)); % update the text box

mat=contig(lat,long,seuil); % computes the new matrix
WX=mat*vglob;

%stdvar=variable/std(variable,1);

Iloc=Ilocal(stdvar,mat);
Iloc=Iloc';
const=ones(length(vglob),1);
res=nonormmoran(stdvar,const,mat);
Imoran=[res.morani];
pvalue=1-norm_cdf(Imoran,0,1);
Q1=find(vglob>0 & WX>0);
Q2=find(WX>0 & vglob<0);
Q3=find(WX<0 & vglob<0);
Q4=find(vglob>0 & WX<0);
set(Ht,'String',['Moran index:',num2str(Imoran)]);
set(Ht2,'String',['p-value:',num2str(pvalue)]);
reg=ols(WX,vglob);

subplot(1,2,2);
hold on;
P=findobj('Color','yellow','LineStyle','-'); % delete the old curve
delete(P);
 plot(vglob,reg.beta*vglob,'y')% trace the new curve
hold off;