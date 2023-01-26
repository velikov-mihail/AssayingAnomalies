function [out]=semmap(long,lat,xinp,yinp,W,varargin)
% PURPOSE: adjust a spatial error model on a subregion selected on the map
%--------------------------------------------------------------
% USAGE: out = semmap(long,lat,xinp,yinp,W,carte,label,symbol)
%   where: 
%          long = n x 1 vector of coordinates on the first axis
%          lat = n x 1 vector of coordinates on the second axis
%          xinp = explanatory variable (matrix n x p)  
%          yinp = n x 1 vector of the dependent variable
%          W = contiguity matrix
%          vnames  = an optional vector of variable names,
%                    e.g. vnames = strvcat('y','const','x1','x2');
%          carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%          label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%--------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%--------------------------------------------------------------
% MANUAL: Select points on the map by clicking with the left mouse button
%         You can select points inside a polygon: - right click to set the first point of the polygon
%                                                 - left click to set the other points
%                                                 - right click to close the polygon
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses sem.m, selectmap.m
%-----------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr-

close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
info.lflag=0;
c=0;
l=0;
symbol=0;
vectx=[];
vecty=[];
vnames_flag = 0;
nbev=size(xinp,2);
results=sem(yinp,xinp,W,info);
dname=inputname(4);
%creation of a menu to save
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save sirfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%

% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        vnames = varargin{1,:};
        vnames_flag = 1;
    end;
    if  t>=2 & ~isempty(varargin{2})
        carte=varargin{2};
        c=1;
    end;
    if  t>=3 & ~isempty(varargin{3})
        label=varargin{3};
        l=1;
    end;
    if t==4 & ~isempty(varargin{4})
        symbol=varargin{4};
    end;
end;
%%%%%%%%%%%%%%%%%%%%%

%Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
axis manual;
%%%%%%%%%%%%%%%%%%%%%

Htitleglob=uicontrol('Style','text','Units','Normalized','Position',[0.66,0.94,0.047,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String','Global','enable','inactive');
Hbhatglob=uicontrol('Style','text','Units','Normalized','Position',[0.6,0.9,0.047,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String','beta','enable','inactive');
Htstatglob=uicontrol('Style','text','Units','Normalized','Position',[0.7,0.9,0.047,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String','t-stat','enable','inactive');
set(Hbhatglob,'FontSize',4,'HorizontalAlignment','right');
set(Htstatglob,'FontSize',4,'HorizontalAlignment','right');

Hbhatglobp=zeros(nbev,1);
Htstatglobp=zeros(nbev,1);
for i=1:nbev
   if vnames_flag == 1
    Hbhatglobp(i)=uicontrol('Style','text','Units','Normalized','Position',[0.55,0.88-(i-1)*0.02,0.070,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String',strjust(vnames(i+1,1:10),'left'),'enable','inactive');
   set(Hbhatglobp(i),'FontSize',4,'HorizontalAlignment','left');
   end;
    Hbhatglobp(i)=uicontrol('Style','text','Units','Normalized','Position',[0.61,0.88-(i-1)*0.02,0.047,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String',strjust(num2str(roundoff(results.beta(i),4)),'left'),'enable','inactive');
    Htstatglobp(i)=uicontrol('Style','text','Units','Normalized','Position',[0.71,0.88-(i-1)*0.02,0.047,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String',strjust(num2str(roundoff(results.tstat(i),2)),'right'),'enable','inactive');
    fyb=0.88-(i-1)*0.02;
    set(Hbhatglobp(i),'FontSize',4,'HorizontalAlignment','right');
    set(Htstatglobp(i),'FontSize',4,'HorizontalAlignment','right');
end

Hrhoglob=uicontrol('Style','text','Units','Normalized','Position',[0.6,fyb-0.04,0.12,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String',['Rho=',num2str(results.rho)],'enable','inactive','enable','inactive');
Hsigeglob=uicontrol('Style','text','Units','Normalized','Position',[0.6,fyb-0.08,0.12,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String',['Sige=',num2str(results.sige)],'enable','inactive','enable','inactive');
Hrbarglob=uicontrol('Style','text','Units','Normalized','Position',[0.6,fyb-0.12,0.12,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String',['Rbar-squared=',num2str(results.rbar)],'enable','inactive');
Hloglikglob=uicontrol('Style','text','Units','Normalized','Position',[0.6,fyb-0.16,0.12,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String',['Log-likelihood=',num2str(results.lik)],'enable','inactive');
Hnobsglob=uicontrol('Style','text','Units','Normalized','Position',[0.6,fyb-0.2,0.12,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String',['Nobservations=',num2str(results.nobs)],'enable','inactive');
set(Hrhoglob,'FontSize',4,'HorizontalAlignment','left');
set(Hsigeglob,'FontSize',4,'HorizontalAlignment','left');
set(Hrbarglob,'FontSize',4,'HorizontalAlignment','left');
set(Hloglikglob,'FontSize',4,'HorizontalAlignment','left');
set(Hnobsglob,'FontSize',4,'HorizontalAlignment','left');

bar=uicontrol('Style','frame','Units','Normalized','Position',[0.77,fyb-0.24,0.001,0.95-fyb+0.24]);
%%%%%%%%%%%%%%%%%%%%%

Htitlesel=uicontrol('Style','text','Units','Normalized','Position',[0.86,0.94,0.047,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String','Selection','enable','inactive');
Hbhatsel=uicontrol('Style','text','Units','Normalized','Position',[0.8,0.9,0.047,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String','beta','enable','inactive');
Htstatsel=uicontrol('Style','text','Units','Normalized','Position',[0.9,0.9,0.047,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String','t-stat','enable','inactive');
set(Hbhatsel,'FontSize',4,'HorizontalAlignment','right');
set(Htstatsel,'FontSize',4,'HorizontalAlignment','right');

Hbhatselp=zeros(nbev,1);
Htstatselp=zeros(nbev,1);
for i=1:nbev
    Hbhatselp(i)=uicontrol('Style','text','Units','Normalized','Position',[0.81,0.88-(i-1)*0.02,0.047,0.026],'Backgroundcolor',[0.8,0.8,0.8],'enable','inactive');
    Htstatselp(i)=uicontrol('Style','text','Units','Normalized','Position',[0.91,0.88-(i-1)*0.02,0.047,0.026],'Backgroundcolor',[0.8,0.8,0.8],'enable','inactive');
    fyb=0.88-(i-1)*0.02;
    set(Hbhatselp(i),'FontSize',4,'HorizontalAlignment','right');
    set(Htstatselp(i),'FontSize',4,'HorizontalAlignment','right');
end

Hrhosel=uicontrol('Style','text','Units','Normalized','Position',[0.8,fyb-0.04,0.12,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String','Rho=','enable','inactive');
Hsigesel=uicontrol('Style','text','Units','Normalized','Position',[0.8,fyb-0.08,0.12,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String','Sige=','enable','inactive');
Hrbarsel=uicontrol('Style','text','Units','Normalized','Position',[0.8,fyb-0.12,0.12,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String','Rbar-squared=','enable','inactive');
Hlogliksel=uicontrol('Style','text','Units','Normalized','Position',[0.8,fyb-0.16,0.12,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String','Log-likelihood=','enable','inactive');
Hnobssel=uicontrol('Style','text','Units','Normalized','Position',[0.8,fyb-0.2,0.12,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String','Nobservations=','enable','inactive');
set(Hrhosel,'FontSize',4,'HorizontalAlignment','left');
set(Hsigesel,'FontSize',4,'HorizontalAlignment','left');
set(Hrbarsel,'FontSize',4,'HorizontalAlignment','left');
set(Hlogliksel,'FontSize',4,'HorizontalAlignment','left');
set(Hnobssel,'FontSize',4,'HorizontalAlignment','left');
if vnames_flag == 1
Hdtitle=uicontrol('Style','text','Units','Normalized','Position',[0.6,fyb-0.35,0.24,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String',['Dependant variable:',vnames(1,1:10)],'enable','inactive');
else
Hdtitle=uicontrol('Style','text','Units','Normalized','Position',[0.6,fyb-0.35,0.24,0.026],'Backgroundcolor',[0.8,0.8,0.8],'String',['Dependant variable:',dname],'enable','inactive');
end;

%%%%%%%%%%%%%%%%%%%%%
% Main loop
BUTTON=0;
oldobs=obs;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    % update
    if ~isequal(oldobs,obs) & ~isempty(Iselect)
        results=sem(yinp(Iselect),xinp(Iselect,:),W(Iselect,Iselect),info);
        for i=1:nbev
            set(Hbhatselp(i),'String',strjust(num2str(roundoff(results.beta(i),4)),'right'));
            set(Htstatselp(i),'String',strjust(num2str(roundoff(results.tstat(i),2)),'right'));
        end;
        set(Hrhosel,'String',['Rho=',strjust(num2str(roundoff(results.rho,4)),'left')]);
        set(Hsigesel,'String',['Sige=',strjust(num2str(roundoff(results.sige,4)),'left')]);
        set(Hrbarsel,'String',['Rbar-squared=',strjust(num2str(roundoff(results.rbar,4)),'left')]);
        set(Hlogliksel,'String',['Log-likelihood=',strjust(num2str(roundoff(results.lik,4)),'left')]);
        set(Hnobssel,'String',['Nobservations=',num2str(results.nobs)]);

    elseif isempty(Iselect)
        for i=1:nbev
            set(Hbhatselp(i),'String','');
            set(Htstatselp(i),'String','');
        end;
        set(Hrhosel,'String','Rho=');
        set(Hsigesel,'String','Sige=');
        set(Hrbarsel,'String','Rbar-squared=');
        set(Hlogliksel,'String','Log-likelihood=');
        set(Hnobssel,'String','Nobservations=');
    end;
    %redraw the graphs
    hold off;
    subplot(Axis1);
    hold on;
    cla;
    if c==1
            plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;
    if ~isempty(Iselect)
        if symbol==1
            plot(long(Iselect),lat(Iselect),'b*');
        else
            plot(long(Iselect),lat(Iselect),'r.');
        end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    oldobs=obs;
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        % point selection
        if BUTTON~=3 & BUTTON~=2
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');
        %%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        end;
        %%%%%%%%%%%%%%%%%
    % bar plot selection
    elseif (currentpoint(1)<PosAx1(1)*Posfig(3)-20) | (currentpoint(1)>(PosAx1(1)+PosAx1(3))*Posfig(3)+20) | (currentpoint(2)<PosAx1(2)*Posfig(4)-20) | (currentpoint(2)>(PosAx1(2)+PosAx1(4))*Posfig(4)+20)
        obs=zeros(size(long,1),1);
    end;
    %%%%%%%%%%%%%%%%%%
end;
out=obs;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%