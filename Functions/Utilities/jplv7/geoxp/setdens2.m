% Callback function for the slider created in densitymap.m
% Not usable outside this context
%-----------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr-

global Hslide;
global Ht;
global vglobal;
global newx;
global dens;
global h;

alph=get(Hslide,'Value');
set(Ht,'String',[num2str(alph),'%']); % update the text box
h=(alph/100)*(max(vglobal)-min(vglobal))/2;
if h==0
    set(Hslide,'Value',1);
    h=(get(Hslide,'Value')/100)*(max(vglobal)-min(vglobal))/2;
end;
dens=kern_den(vglobal,h,newx); % computes the new curve
subplot(1,2,2);
hold on;
P=findobj('Color','blue','LineStyle','-'); % delete the old curve
delete(P);
plot(newx,dens,'b'); % trace the new curve
hold off;