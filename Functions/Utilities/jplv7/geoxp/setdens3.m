% Callback function for the sliders created in dbledensitymap.m
% Not usable outside this context
%-----------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr-

global v1glob;
global h1;
global v2glob;
global h2;
global Hslide1;
global Ht1;
global Hslide2;
global Ht2;
global newx;
global dens;
global newx2;
global dens2;
a1=get(Hslide1,'Value');
set(Ht1,'String',[num2str(a1),'%']); % update the first text box
h1=(a1/100)*(max(v1glob)-min(v1glob))/2;
if h1==0
    set(Hslide1,'Value',1);
    h1=(get(Hslide1,'Value')/100)*(max(v1glob)-min(v1glob))/2;
end;
dens=kern_den(v1glob,h1,newx); % computes the new curve for Axis2
subplot(2,2,2);
hold on;
P=findobj('Color','blue','LineStyle','-'); % delete the old curves
delete(P);
plot(newx,dens,'b'); % trace the new curve for Axis2
hold off;

a2=get(Hslide2,'Value');
set(Ht2,'String',[num2str(a2),'%']); % update the second text box
h2=(a2/100)*(max(v2glob)-min(v2glob))/2;
if h2==0
    set(Hslide2,'Value',1);
    h2=(get(Hslide2,'Value')/100)*(max(v2glob)-min(v2glob))/2;
end;
dens2=kern_den(v2glob,h2,newx2); % computes the new curve for Axis3
subplot(2,2,4);
hold on;
plot(newx2,dens2,'b'); % trace the new curve for Axis3
hold off;