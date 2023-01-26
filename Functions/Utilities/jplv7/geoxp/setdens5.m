% Callback function for the slider created in angleplotmap.m
% Not usable outside this context
%-----------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr-

global Hslide;
global Ht;
global v1glob;
global eval;
global v2glob;
global eval;
global r;
alph=get(Hslide,'Value');
set(Ht,'String',[num2str(alph),'%']); % update the text box
h=(alph/100)*(max(v1glob)-min(v1glob))/2;
if h==0
    set(Hslide,'Value',1);
    h=(get(Hslide,'Value')/100)*(max(v1glob)-min(v1glob))/2;
end;
r=kern_re(v1glob',v2glob',h,eval'); % computes the new curve
subplot(1,2,2);
hold on;
P=findobj('Color','yellow'); % delete the old curve
delete(P);
plot(eval',r,'y'); % trace the new curve
hold off;